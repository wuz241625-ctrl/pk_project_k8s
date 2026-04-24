<?php

include('HttpGo.php');
class Tool
{
    public static  $httpProxy = "127.0.0.1:10809";
    //CsrfId请求
    public function getCsrfId($httpProxy)
    {
        $url = "https://www.freecharge.in/api/ims/rest/create/csrf";
        $res_arr = HttpGo::httpGet($url, '', [], $httpProxy);
        $body = json_decode($res_arr["data"]["body"], true);
        $csrfRequestIdentifier = $body["csrfRequestIdentifier"];
        $cookiesString = $res_arr["data"]["cookies"];
        return [
            "csrfRequestIdentifier" => $csrfRequestIdentifier,
            "app_fc" => getCookie("app_fc", $cookiesString),
        ];
    }

    // key请求

    public function getKey($httpProxy)
    {
        $url = "https://www.freecharge.in/api/ems/nosession/v2/external/encryption/generatekeys";
        $res_arr = HttpGo::httpPost($url, "{}", $httpProxy, []);
        $body = json_decode($res_arr["data"]["body"], true);
        return $body;
    }

    //登录验证码请求
    public function loginCaptcha($phoneNum, $cookies, $pke, $csrfRequestIdentifier, $httpProxy)
    {

        $url = "https://www.freecharge.in/api/ims/rest/otp/send/login/signup";
        //POST数据格式：{"mobileNumber":"RlJFRUNIQVJHRV9WMnxIQkZKd1BKeVRYNzlFWlA5L3drOTFLazhiWHhDeVp3cDlMTT0=","fcChannel":12,"platformType":"WEB"}
        $key = self::rr(22);
        $phoneNum = self::ll($phoneNum, $key);
        $data = [
            "mobileNumber" => $phoneNum,
            "fcChannel" => 12,
            "platformType" => "WEB"
        ];
        $dataString = json_encode($data);
        $rsaKey = explode('|', $pke)[0];
        $cske = self::o($key, $rsaKey);
        $headers = [
            "pke" => $pke,
            "cske" => $cske,
            "csrfRequestIdentifier" => $csrfRequestIdentifier,
            "fcChannel" => "12",
            "Cookie" => $cookies,
        ];
        $res_arr = HttpGo::httpPost($url, $dataString, $httpProxy, '', $headers);
        return $res_arr["data"]["body"];
    }

    //登录请求
    public function loginWithCode($otpId, $otp, $cookies, $csrfRequestIdentifier, $httpProxy)
    {
        $url = "https://www.freecharge.in/api/ims/rest/mobileOnly/verify";
        //POST数据格式：{"otpId":"992b256c-4ed9-4ca4-ae13-7e379ffa600d","otp":"5147","fcChannel":12,"platformType":"WEB","assignedClientId":"","visitId":"","increaseTokenSession":true}
        $data = [
            "otpId" => $otpId,
            "otp" => $otp,
            "assignedClientId" => "",
            "visitId" => "",
            "fcChannel" => 12,
            "platformType" => "WEB",
            "increaseTokenSession" => true
        ];
        $dataString = json_encode($data);
        echo $dataString . "\n";
        $headers = [
            "csrfRequestIdentifier" => $csrfRequestIdentifier,
            "Cookie" => $cookies,
            "fcChannel" => "12",
        ];
        $res_arr = HttpGo::httpPost($url, $dataString, $httpProxy, '', $headers);
        echo json_encode($res_arr) . "\n";
        return $res_arr; //$res_arr["data"]["body"];
    }

    //getUpi
    function getUpi($cookies, $csrfRequestIdentifier, $httpProxy)
    {
        $url = "https://www.freecharge.in/rest/upi/v2/upistatus";
        $dataString = '{"device":{"app":"","id":""}}';
        $headers = [
            "csrfRequestIdentifier" => $csrfRequestIdentifier,
            "Cookie" => $cookies,
        ];
        $res_arr = HttpGo::httpPost($url, $dataString, $httpProxy, '', $headers);
        echo json_encode($res_arr) . "\n";
        return $res_arr; //$res_arr["data"]["body"];
    }

    //监听账单
    public function listenPay($cookies, $httpProxy)
    {
        echo "开始监听账单【5秒更新一次】\n\n";
        $url = "https://www.freecharge.in/thv/moneydirection";
        //POST数据格式：{"direction":null}
        $data = ["direction" => null];
        $dataString = json_encode($data);
        while (true) {
            $res_arr = HttpGo::httpPost($url, $dataString, $httpProxy, $cookies);
            $res = $res_arr["data"]["body"];
			echo "输出第一页账单：".$res;
            $res_json = json_decode($res, true);
            $timestamp = $res_json['data'][0]['timestamp'];
            $txnAmount = $res_json['data'][0]['txnAmount'];
            $txnType = $res_json['data'][0]['txnType'];
            $globalTxnType = $res_json['data'][0]['globalTxnType'];
            $globalTxnId = $res_json['data'][0]['globalTxnId'];
            $timestampFormatted = date("Y-m-d H:i:s", $timestamp / 1000);
            //....
            $currentDateTime = date("Y-m-d H:i:s");
            echo ("====最新一笔交易====\n" .
                "时间：" . $timestampFormatted . "\n" .
                "金额：" . $txnAmount . "\n" .
                "类型：" . $txnType . "\n" .
                "globalTxnType：" . $globalTxnType . "\n" .
                "globalTxnId：" . $globalTxnId . "\n" .
                "====" . $currentDateTime . "更新========\n");
            // 等待 5 秒
            sleep(5);
        }
    }
    //
    function ll($str, $key)
    {
        $data = self::l($str, $key);
        return base64_encode("FREECHARGE_V2|" . $data);
    }
    //
    function l($data, $key)
    {
        $cipher = 'aes-128-gcm';
        $hashkey = substr(hash('sha256', $key), 0, 32);
        echo $hashkey.PHP_EOL;
        $skey = hex2bin($hashkey);
        $iv = hex2bin("000000000000000000000000");
        echo "11111".$iv.PHP_EOL;
        $tag = NULL;
        $content = openssl_encrypt($data, $cipher, $skey, OPENSSL_RAW_DATA, $iv, $tag);
        echo $content.PHP_EOL;
        $str =  bin2hex($content) . bin2hex($tag);
        echo $str.PHP_EOL;
        return base64_encode(hex2bin($str));
    }

    //解密
    function k($data, $secret)
    {
        $cipher = 'aes-128-gcm';
        $skey = hex2bin($secret);
        $iv = hex2bin("000000000000000000000000");
        $tag = NULL;
        $str = bin2hex(base64_decode($data));
        $content = hex2bin(substr($str, 0, -32));
        $tag = hex2bin(substr($str, -32));
        return openssl_decrypt($content, $cipher, $skey, OPENSSL_RAW_DATA, $iv, $tag);
    }

    function o($data, $secret)
    {
        $public_key = "-----BEGIN PUBLIC KEY-----\n$secret\n-----END PUBLIC KEY-----"; //公钥内容 
        openssl_public_encrypt($data, $encrypted_data, $public_key, OPENSSL_PKCS1_PADDING);
        $encBase64_data = base64_encode($encrypted_data);
        return base64_encode("FREECHARGE_V2|" . $encBase64_data);
    }

    //生成随机字符串
    function rr($length)
    {
        $characters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
        $string = '';
        $characterCount = strlen($characters);

        for ($i = 0; $i < $length; $i++) {
            $string .= $characters[random_int(0, $characterCount - 1)];
        }

        return $string;
    }
}
