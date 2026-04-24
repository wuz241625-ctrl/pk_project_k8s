<?php
include('Tool.php');
$tool = new Tool();
$httpProxy = "socks5:socks5@148.113.3.134:5555";
$key_arr = $tool->getKey($httpProxy);
$pke = $key_arr['data']['keys'][0]['key']; //
$startTime = $key_arr['data']['keys'][0]['startTime'];
$expiryTime = $key_arr['data']['keys'][0]['expiryTime'];
if (empty($pke) || empty($startTime)) {
    die("获取pke失败" . json_encode($key_arr));
}

//echo "pke: " . $pke . "\n";
echo "Start Time: " . $startTime . "\n";
echo "Expiry Time: " . $expiryTime . "\n";

//////
$csrfId_arr = $tool->getCsrfId($httpProxy);
$app_fc = $csrfId_arr["app_fc"];
$csrfId = $csrfId_arr["csrfRequestIdentifier"]; //
if (empty($app_fc) || empty($csrfId)) {
    die("获取csrfId失败");
}
echo "app_fc: " . $app_fc . "\n";
echo "csrfId: " . $csrfId . "\n";
/////////

//$phone = "9694717429";
echo "请输入手机号码：";
$phone = trim(readline()); // 等待用户输入，

$cookies = "app_fc=" . $app_fc . ";_ga=GA1.1.590881904.1706179398;_ga_Q9NVXVJCL0=GS1.1.1706234979.2.0.1706234979.0.0.0; moe_uuid=693976e7-8977-445a-ac17-50fb5797098a";
//登录验证码请求
$code_str = $tool->loginCaptcha($phone, $cookies, $pke, $csrfId, $httpProxy);
$code_json = json_decode($code_str, true);
if ($code_json['data'] === null) {
    $error_code = $code_json['error']['errorCode'];
    $error_message = $code_json['error']['errorMessage'];
    echo "验证码请求出错 :错误码:" . $error_code . ",错误信息: " . $error_message . "\n";
} else {
    $optid = $code_json['data']['otpId'];
    echo "验证码请求成功 :otpId:" . $optid . "\n";
}

echo "请输入验证码：";
$phoneCode = trim(readline()); // 等待用户输入，
$res_arr = $tool->loginWithCode($optid, $phoneCode, $cookies, $csrfId, $httpProxy);

$login_json = $res_arr["data"]["body"];
//echo "登录请求成功: " . json_encode($body) . "\n";
$cookiesString =$res_arr["data"]["cookies"];
$app_fc_ = getCookie("app_fc", $cookiesString);


//监听账单
if (empty($app_fc_)) {
    die("无法监听账单");
}
//$app_fc_="uE7hVQspD47b02A-fZuobIBqivXVp7LZG1pdiDikwYFzhdO2vvJvW0huVtomk3L2d8bmI-VA0nAJuqH7ns2Ry--C1A47ccn9_eBZk1-HX9o0qNLIIoXqxbtRF3q6k4mJ";
$cookies = "_ga=GA1.1.768328936.1706099429; moe_uuid=af80e942-62e3-45e7-b022-4527eb8ecaa2; _ga_Q9NVXVJCL0=GS1.1.1706099429.1.1.1706099537.0.0.0; app_fc=" . $app_fc_;
var_dump($cookies);
$tool->listenPay($cookies, $httpProxy);
