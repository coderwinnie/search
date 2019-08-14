// _______________
// Canvas-Designer

// Open-Sourced: https://github.com/muaz-khan/Canvas-Designer

// --------------------------------------------------
// Muaz Khan     - www.MuazKhan.com
// MIT License   - www.WebRTC-Experiment.com/licence
// --------------------------------------------------

function CanvasDesigner() {
    var designer = this;
    designer.iframe = null;
    designer.isLocalMobile = false;
    designer.isRemoteMobile = false;
    var isSync = null;
    var tools = {
        line: true,
        arrow: true,
        pencil: true,

        dragSingle: true,
        dragMultiple: true,
        eraser: true,
        rectangle: true,
        arc: true,
        bezier: true,
        quadratic: true,
        text: true,
        image: true,
        pdf: true,
        marker: true,
        zoom: true,
        lineWidth: true,
        colorsPicker: true,
        extraOptions: true,
        code: true
    };

    designer.icons = {
        line: null,
        arrow: null,
        pencil: null,
        dragSingle: null,
        dragMultiple: null,
        eraser: null,
        rectangle: null,
        arc: null,
        bezier: null,
        quadratic: null,
        text: null,
        image: null,
        pdf: null,
        pdf_next: null,
        pdf_prev: null,
        pdf_close: null,
        marker: null,
        zoom: null,
        lineWidth: null,
        colorsPicker: null,
        extraOptions: null,
        code: null
    };

    var selectedIcon = 'pencil';

    function syncData(data) {
        if (!designer.iframe) return;
        if (!data) {
            designer.renderStream();
        }
        designer.postMessage({
            canvasDesignerSyncData: data
        });
    }

    var syncDataListener = function (data) {
    };
    var syncKeyListener = function (data) {
    };
    var dataURLListener = function (dataURL) {
    };
    var captureStreamCallback = function () {
    };
    designer.isSync = null;
    // function tryagain(event){
    //     if (!event.data || event.data.uid !== designer.uid) {
    //         designer.renderStream();
    //         return;
    //     }
    //     if(!!event.data.sdp) {
    //         webrtcHandler.createAnswer(event.data, function(response) {
    //             if(response.sdp) {
    //                 designer.postMessage(response);
    //                 return;
    //             }
    //
    //             captureStreamCallback(response.stream);
    //         });
    //         return;
    //     }
    //
    //     if (!!event.data.canvasDesignerSyncData) {
    //         designer.pointsLength = event.data.canvasDesignerSyncData.points.length;
    //         if(designer.isSync === null){
    //             designer.renderStream();
    //             designer.sync();
    //             designer.isSync = true;
    //         }
    //         syncDataListener(event.data.canvasDesignerSyncData);
    //         return;
    //     }
    //
    //     if (!!event.data.dataURL) {
    //         dataURLListener(event.data.dataURL);
    //         return;
    //     }
    // }
    function onMessage(event) {
        if (designer.isSync === null) {
            designer.renderStream();
            designer.sync();
            designer.isSync = true;
        }
        if (!event.data || event.data.uid !== designer.uid) {
            try {
                var data_ = parseJSON(event.data)
                if (data_.uid !== designer.uid) {
                    return
                }
            } catch (e) {
                return
            }
            if (!!data_.key) {
                window.appController.onCanvasKeyPress_(data_.key);
            }else if(!!data_.scaleW){
                document.getElementById("videos").style.width = data_.scaleW;
                // designer.iframe.style.width = data_.scaleW * designer.iframe.scrollWidth;
                designer.iframe.style.width = (parseFloat(data_.scaleW)/100 * designer.iframe.scrollWidth) + "px";
                window.appController.onVideoSizeChanged();
            }else if(!!data_.scaleH){
                document.getElementById("videos").style.height = data_.scaleH;
                // designer.iframe.style.height = data_.scaleH * designer.iframe.scrollHeight;
                designer.iframe.style.height = (parseFloat(data_.scaleH)/100 * designer.iframe.scrollHeight) + "px";
                window.appController.onVideoSizeChanged();
            }else if (!!data_.cleanAll){
                designer.undo('all');
                designer.isPdf = null;
                // designer.sync();
            }else if(!!data_.toW){
                document.getElementById("videos").style.width = data_.toW;
                window.appController.onVideoSizeChanged();
            }else if(!!data_.toH){
                document.getElementById("videos").style.height = data_.toH;
                window.appController.onVideoSizeChanged();
            }else if (!!data_.onNewPdf){
                designer.changeSize();
                designer.isPdf = true;
            }else if (!!data_.getResolution){
                designer.changeSize();
            }
            // designer.renderStream();
            // tryagain(event);
        }

        if (!!event.data.sdp) {
            webrtcHandler.createAnswer(event.data, function (response) {
                if (response.sdp) {
                    designer.postMessage(response);
                    return;
                }

                captureStreamCallback(response.stream);
            });
            return;
        }

        if (!!event.data.canvasDesignerSyncData) {
            designer.pointsLength = event.data.canvasDesignerSyncData.points.length;
            // if(designer.isSync === null){
            //     designer.renderStream();
            //     designer.sync();
            //     designer.isSync = true;
            // }
            syncDataListener(event.data.canvasDesignerSyncData);
            return;
        }

        if (!!event.data.dataURL) {
            dataURLListener(event.data.dataURL);
            return;
        }

    }

    function getRandomString() {
        if (window.crypto && window.crypto.getRandomValues && navigator.userAgent.indexOf('Safari') === -1) {
            var a = window.crypto.getRandomValues(new Uint32Array(3)),
                token = '';
            for (var i = 0, l = a.length; i < l; i++) {
                token += a[i].toString(36);
            }
            return token;
        } else {
            return (Math.random() * new Date().getTime()).toString(36).replace(/\./g, '');
        }
    }

    designer.uid = getRandomString();

    designer.getSyncFunc = function () {
        console.log(syncDataListener);
    };

    designer.isPdf = null;
    var resolutionCache;

    designer.changeSize = function () {
        var w,h;
        var resolutionDict_ = window.resolutionDict;
        designer.iframe.style.width = w;
        designer.iframe.style.height = h;

        if(designer.isPdf){
            debugger;
            var tempVideo_ = document.getElementById("videos");
            if(designer.iframe.scrollHeight < tempVideo_.scrollHeight){
                designer.iframe.style.height = tempVideo_.scrollHeight + "px";
            }
            if(designer.iframe.scrollWidth < tempVideo_.scrollWidth){
                designer.iframe.style.width = tempVideo_.scrollWidth + "px";
            }
            return; //TODO：要不要加postmessage？
            if(resolutionCache){
                w = resolutionCache['localw'];
                h = resolutionCache['localh'];
            }else{
                w = "100%";
                h = "100%";
            }
        }else{
            w = "100%";
            h = "100%";
        }
        // designer.iframe.style.width = w;
        // designer.iframe.style.height = h;
        console.log(window.resolutionDict);
        var wscale = resolutionDict_['remotew'] / resolutionDict_['localw'];
        var hscale = resolutionDict_['remoteh'] / resolutionDict_['localh'];
        if (wscale >= 1 && hscale >= 1) {
            designer.iframe.style.width = w;
            designer.iframe.style.height = h;
            console.log("remote bigger")
            // window.scale = 1;
        } else if (wscale >= 1 || hscale >= 1) {
            if (hscale < wscale) {//对面的width大与本地
                // w = (100 * wscale).toFixed(1) + "%";
                designer.iframe.style.height = resolutionDict_['remoteh'] + "px";
                designer.iframe.style.width = w;
            } else if (hscale > wscale) {
                // h = (100 * hscale).toFixed(1) + "%";
                designer.iframe.style.width = resolutionDict_['remotew'] + "px";
                designer.iframe.style.height = h;
            }
            // window.scale = wscale > hscale ? hscale : wscale;
        } else if (0 < wscale && wscale < 1 && 0 < hscale && hscale < 1) {
            designer.iframe.style.width = resolutionDict_['remotew'] + "px";
            designer.iframe.style.height = resolutionDict_['remoteh'] + "px";
            // w = (100 * wscale).toFixed(1) + "%";
            // h = (100 * hscale).toFixed(1) + "%";
            console.log("this bigger")
            // window.scale = wscale > hscale ? hscale : wscale;
        }
        // designer.iframe.style.width = w;
        // designer.iframe.style.height = h;

        // designer.postMessage(JSON.stringify({
        //     resolutionDict_: resolutionDict_
        // }));
        if (!designer.iframe || typeof designer.postMessage != "function") return;

        designer.postMessage({
            resolutionDict_: resolutionDict_
        });
        resolutionCache = resolutionDict_;
    };


    // designer.changeSize = function () {
    //     debugger;
    //     var w = "100%";
    //     var h = "100%";
    //     designer.iframe.style.width = w;
    //     designer.iframe.style.height = h;
    //     console.log(window.resolutionDict);
    //     var resolutionDict_ = window.resolutionDict;
    //     var wscale = resolutionDict_['remotew'] / resolutionDict_['localw'];
    //     var hscale = resolutionDict_['remoteh'] / resolutionDict_['localh'];
    //     if (wscale > 1 && hscale > 1) {
    //         window.scale = 1;
    //     } else if (wscale > 1 || hscale > 1) {
    //         if (wscale < hscale) {
    //             w = (100 * wscale).toFixed(1) + "%";
    //             designer.iframe.style.width = resolutionDict_['remotew'];
    //         } else if (hscale < wscale) {
    //             h = (100 * hscale).toFixed(1) + "%";
    //             designer.iframe.style.height = resolutionDict_['remoteh'];
    //         }
    //         // window.scale = wscale > hscale ? hscale : wscale;
    //     } else if (0 < wscale && wscale < 1 && 0 < hscale && wscale < 1) {
    //         // w = (100 * wscale).toFixed(1) + "%";
    //         // h = (100 * hscale).toFixed(1) + "%";
    //         designer.iframe.style.width = resolutionDict_['remotew'];
    //         designer.iframe.style.height = resolutionDict_['remoteh'];
    //         // window.scale = wscale > hscale ? hscale : wscale;
    //     }
    //     // designer.iframe.style.width = w;
    //     // designer.iframe.style.height = h;
    //
    //     // designer.postMessage(JSON.stringify({
    //     //     resolutionDict_: resolutionDict_
    //     // }));
    //     debugger;
    //     if (!designer.iframe || typeof designer.postMessage != "function") return;
    //
    //     designer.postMessage({
    //         resolutionDict_: resolutionDict_
    //     });
    // };

    designer.appendTo = function (parentNode, callback) {
        callback = callback || function () {
        };
        console.log(callback);
        designer.iframe = document.createElement('iframe');
        designer.iframe.id = "canvasDesigner";

        // designer load callback
        designer.iframe.onload = function () {
            callback();
            callback = null;
            designer.postMessage({
                isRemoteMobile: designer.isRemoteMobile
            });
        };

        designer.iframe.src = designer.widgetHtmlURL + '?widgetJsURL=' + designer.widgetJsURL + '&tools=' + JSON.stringify(tools) + '&selectedIcon=' + selectedIcon + '&icons=' + JSON.stringify(designer.icons);

        // 调整大小

        designer.changeSize();
        // designer.iframe.style.width = resResult[0];
        // designer.iframe.style.height = resResult[1];

        // designer.iframe.style.width = '100%';
        // designer.iframe.style.height = '100%';
        // console.log(window.resolutionDict);
        // var resolutionDict_ = window.resolutionDict;
        // var wscale = resolutionDict_['remotew'] / resolutionDict_['localw'];
        // var hscale = resolutionDict_['remoteh'] / resolutionDict_['localh'];
        // if (wscale > 1 && hscale > 1) {
        //     window.scale = 1;
        // } else if (wscale > 1 || hscale > 1) {
        //     if(wscale<hscale){
        //         designer.iframe.style.width = 100*wscale + "%";
        //     }else if (hscale<wscale){
        //         designer.iframe.style.height = 100*hscale + "%";
        //     }
        //     // window.scale = wscale > hscale ? hscale : wscale;
        // } else if (0 < wscale < 1 && 0 < hscale < 1) {
        //     designer.iframe.style.width = 100*wscale + "%";
        //     designer.iframe.style.height = 100*hscale + "%";
        //     // window.scale = wscale > hscale ? hscale : wscale;
        // }

        designer.iframe.style.border = 0;

        window.removeEventListener('message', onMessage);
        window.addEventListener('message', onMessage, false);

        parentNode.appendChild(designer.iframe);


        // parentNode.insertBefore(designer.iframe, document.getElementById("mini-video"))
    };

    designer.destroy = function () {
        if (designer.iframe) {
            designer.iframe.parentNode.removeChild(designer.iframe);
            designer.iframe = null;
        }
        designer.isSync = null;
        window.removeEventListener('message', onMessage);
    };

    designer.addSyncListener = function (callback) {
        console.warn(callback);
        syncDataListener = callback;
    };


    designer.addKeyListener = function (callback) {
        console.warn(callback);
        syncKeyListener = callback;
    };

    designer.syncData = syncData;

    designer.setTools = function (_tools) {
        tools = _tools;
    };

    designer.setSelected = function (icon) {
        if (typeof tools[icon] !== 'undefined') {
            selectedIcon = icon;
        }
    };

    designer.toDataURL = function (format, callback) {
        dataURLListener = callback;

        if (!designer.iframe) return;
        designer.postMessage({
            genDataURL: true,
            format: format
        });
    };

    designer.sync = function () {
        if (!designer.iframe) return;
        designer.postMessage({
            syncPoints: true
        });
    };

    designer.pointsLength = 0;

    designer.undo = function (index) {
        if (!designer.iframe) return;

        if (typeof index === 'string' && tools[index]) {
            designer.postMessage({
                undo: true,
                tool: index
            });
            return;
        }

        designer.postMessage({
            undo: true,
            index: index || designer.pointsLength - 1 || -1
        });
    };

    designer.postMessage = function (message) {
        // if (!designer.iframe) return;
        if (!designer.iframe || !designer.iframe.contentWindow || !designer.iframe.contentWindow.postMessage) return;
        // if (!message){
        //     designer.renderStream()
        // }
        message.uid =
            designer.uid;
        designer.iframe.contentWindow.postMessage(message, '*');
    };

    designer.captureStream = function (callback) {
        if (!designer.iframe) return;

        captureStreamCallback = callback;
        designer.postMessage({
            captureStream: true
        });
    };

    designer.clearCanvas = function () {
        if (!designer.iframe) return;

        designer.postMessage({
            clearCanvas: true
        });
    };

    designer.renderStream = function () {
        if (!designer.iframe) return;

        designer.postMessage({
            renderStream: true
        });
    };

    designer.widgetHtmlURL = 'widget.html';
    designer.widgetJsURL = 'widget.min.js';


}
