#!/usr/bin/env bash
#!/bin/sh
## 单人音视频部署
set -e
# helps
help_display(){
    echo "install_video.sh: script [options...] [location]"
    echo -h "       show help pages"
    echo -s "       using tls for server, close on default"
    echo -p "       needed if -s, input pem file location"
    echo -k "       needed if -s, input key file location"
    exit 0
}

# 检查启动参数
IF_TLS=false
PEM_FILE=false
KEY_FILE=false
while getopts 'hsp:k:' c;
do
    case $c in
        h) help_display ;;
        s) IF_TLS=true ;;
        p) PEM_FILE=$OPTARG ;;
        k) KEY_FILE=$OPTARG ;;
    esac
done
if [ $IF_TLS = true ];then
    if [ -f $PEM_FILE ]; then
        echo "证书PEM文件地址未找到, 请重新输入..."
        exit 0
    fi
    if [ -f $KEY_FILE ]; then
        echo "证书KEY文件地址未找到, 请重新输入..."
        exit 0
    fi
fi


# check源文件
sudo mkdir -p /startalk/download/single_video
cd /startalk/download/single_video
sudo chown -R startalk:startalk  /startalk

if [ ! -f "/startalk/download/single_video/go1.12.7.linux-amd64.tar.gz" ]; then
    wget https://dl.google.com/go/go1.12.7.linux-amd64.tar.gz
fi
if [ ! -d "/usr/local/go" ]; then
    tar -C /usr/local -xzf /startalk/download/single_video/go1.12.7.linux-amd64.tar.gz
else
    rm -rf /usr/local/go
    tar -C /usr/local -xzf /startalk/download/single_video/go1.12.7.linux-amd64.tar.gz
fi
if [ ! -d "/startalk/download/single_video/coturn" ]; then
    git clone https://github.com/coturn/coturn.git
fi
if [ ! -d "/startalk/download/single_video/apprtc" ]; then
    git clone https://github.com/webrtc/apprtc.git
fi
if [ ! -d "/startalk/download/single_video/net" ]; then
    git clone https://github.com/golang/net.git net
fi

# 部署go环境
# 如果需要修改go工作环境 修改下面这个变量
WORKING_DIR="/startalk/qtalk_video"
GO_WORKING_DIR="/startalk/qtalk_video/go"
mkdir -p ${GO_WORKING_DIR}/src
sudo chown -R startalk:startalk  /startalk

if [ "$GOPATH" = "" ]; then
    printf "\nexport PATH=$PATH:/usr/local/go/bin\nexport GOPATH=${GO_WORKING_DIR}" >> $HOME/.bash_profile
    source $HOME/.bash_profile
fi

# 测试go环境
if [[ $GOPATH = $GO_WORKING_DIR ]]; then
    cd ${GO_WORKING_DIR}
    printf 'package main\nimport "fmt"\nfunc main() {\n\tfmt.Printf("OK")\n}' > ./test.go
    GO_TEST_RESULT=`go run test.go`
    if [[ $GO_TEST_RESULT = "OK" ]]; then
        echo "GO INSTALL SUCCESS"
    else
        echo $GO_TEST_RESULT
        echo "GO INSTALL FAILED, PLEASE CHECK GO WORKING SPACE"
        exit 0
    fi
else
    echo $GOPATH
    echo $WORKING_DIR
    echo "GO INSTALL FAILED, PLEASE CHECK SYSTEM ENVIROMENT"
    exit 0
fi
cd ${WORKING_DIR}

# 部署coturn
# 开好公网ip port:[3478, 59001-65000] tcp + udp 不能用nginx转发
# 开好公网域名 因为项目需要https
cp -r /startalk/download/single_video/coturn ${WORKING_DIR}
sudo yum -y install libevent-devel
sudo yum -y install openssl-devel
cd ${WORKING_DIR}/coturn
./configure
make
make install
printf "listening-port=3478\nalt-listening-port=59000\nlistening-ip=127.0.0.1\nrelay-ip=127.0.0.1\nmin-port=59001\nmax-port=65000\nverbose\nfingerprint\nlt-cred-mech\nuser=qtalk:qtalk\nrealm=qtalk\nlog-file=${WORKING_DIR}/log/turn.log\nmobility\nno-cli" > ./turnserver.conf
if [[ $PEM_FILE != false ]]; then
    printf "\ncert=${PEM_FILE}\n" >> ./turnserver.conf
fi
if [[ $KEY_FILE != false ]]; then
    printf "\npkey=${KEY_FILE}\n" >> ./turnserver.conf
fi

# 启动coturn服务
ps aux | grep turnserver| grep -v "grep" | awk -F' ' '{print $2}'| xargs -I {} sudo kill {}
/usr/local/bin/turnserver -o -c `pwd`/turnserver.conf
sleep 1
ps -ef|grep turnserver|grep -v grep
if [ $? -eq 0 ];then
    echo "COTURN 启动成功..."
else
    echo "COTURN 启动失败..."
    exit 0
fi

# 部署collider服务
# 不要cd进去
cd ${WORKING_DIR}
cp -r /startalk/download/single_video/apprtc ${WORKING_DIR}
# 编辑证书地址
if [[ $PEM_FILE != false ]]; then
    sed -i "68s?/cert/cert\.pem?$PEM_FILE?" ${WORKING_DIR}/apprtc/src/collider/collider/collider.go
fi
if [[ $KEY_FILE != false ]]; then
    sed -i "68s?/cert/key\.pem?$KEY_FILE?" ${WORKING_DIR}/apprtc/src/collider/collider/collider.go
fi

ln -s `pwd`/apprtc/src/collider/collider $GOPATH/src
ln -s `pwd`/apprtc/src/collider/collidermain $GOPATH/src
ln -s `pwd`/apprtc/src/collider/collidertest $GOPATH/src
mkdir -p $GOPATH/src/golang.org/x/
cd $GOPATH/src/golang.org/x/
cp -r /startalk/download/single_video/net ./
go install net

go get collidermain
go install collidermain

# 验证collider信令服务器部署
mkdir -p ${WORKING_DIR}/log
cd ${WORKING_DIR}/log
ps aux | grep collidermain| grep -v "grep" | awk -F' ' '{print $2}'| xargs -I {} sudo kill {}
sudo nohup ${GOPATH}/bin/collidermain -port=8089 -tls=${IF_TLS} &
sleep 1
ps -ef|grep collider|grep -v grep
if [[ $? -eq 0 ]]; then
      ECHO_RESULT=`curl -s '0.0.0.0:8884/rtc/echo'`
      if [[ ECHO_RESULT = "OK" ]]; then
        echo "################################"
        echo "服务正常启动"
        echo "################################"
      fi
else
    echo "COLLIDER 启动失败..."
    tail -20 ${WORKING_DIR}/log/nohup.out
    exit 0
fi
