// build.config.js 变量名要以VUE_APP 开头
module.exports = {
    ospay: {
        common: {
            VUE_APP_SYSTEM: "OSPay",
            VUE_APP_TITLE: "OSPay",
        },
        dev: {
        },
        prod: {
        }
    },
    '789pay': {
        common: {
            VUE_APP_SYSTEM: "789Pay",
            VUE_APP_TITLE: "789Pay",
        },
        dev: {
        },
        prod: {
        }
    },
    d7pay: {
        common: {
            VUE_APP_SYSTEM: "d7pay",
            VUE_APP_TITLE: "D7pay",
            VUE_APP_FAVICON: "d7pay-favicon.ico",
        },
        dev: {
        },
        prod: {
        }
    }
}
