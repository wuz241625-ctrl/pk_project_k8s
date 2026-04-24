<?php

class HttpGo
{
    // http代理
//    private static $httpProxy = "127.0.0.1:1080";

    //socks5 代理
    private static $httpProxy = "socks5:socks5@148.113.3.134:5555";

    private static  $request_header = [
        'Accept' => 'application/json, text/plain, */*',
        'Origin' => 'https://www.freecharge.in',
        'Referer' => 'https://www.freecharge.in/',
        'Content-Type' => 'application/json',
        'User-Agent' => ' Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.87 Safari/537.36',
        'Accept-Language' => 'zh-CN,zh;q=0.9',
        'Connection' => 'keep-alive',
    ];

    public static function httpGet($url, $cookies = "", $request_header = [], $httpProxy)
    {
        $headers = array_merge(self::$request_header, $request_header);
        return sendRequest($url, "GET", [], $cookies, $headers, $httpProxy);
//        return sendRequest($url, "GET", [], $cookies, $headers, self::$httpProxy);
    }

    public static function httpPost($url, $data, $httpProxy, $cookies = "", $request_header = [])
    {
        $headers = array_merge(self::$request_header, $request_header);
        return sendRequest($url, "POST", $data, $cookies, $headers, $httpProxy);
//        return sendRequest($url, "POST", $data, $cookies, $headers, self::$httpProxy);
    }
}

/** 
 * @param    $url            string        路径       如：https://example.com/a/b?key=val&k=>v
 * @param    $method         string        请求方式   如：get、post、put、delete、patch、options
 * @param    $payload        array|string  荷载       如：['foo' => 'bar', 'upload_file' => new CURLFile(file_path)]或json{"foo":"bar"}
 * @param    $cookies        string        cookies    如：cookie1=value1; cookie2=value2; cookie3=value3
 *  @param   $request_header array         请求头     如：['Content-Type' => 'json', 'Set-Cookie' => 'foo']
 * @param    $httpProxy      string        代理设置   如：127.0.0.1:1045
 * @return   array [bool 请求是否成功, string 错误内容, [int http状态码, array 响应头, string 响应主体内容]];
 */
function sendRequest($url, $method = 'GET', $payload = [], $cookies = "", $request_header = [], $httpProxy = "")
{

    $curl = curl_init();
    curl_setopt($curl, CURLOPT_URL, $url);
    if (!empty($httpProxy)) {
//        list($proxyAddress, $proxyPort) = explode(":", $httpProxy, 2);
//        // 设置代理服务器的地址和端口号
//        curl_setopt($curl, CURLOPT_PROXY,  $proxyAddress);
//        curl_setopt($curl, CURLOPT_PROXYPORT,  $proxyPort);

        //使用socks5代理
        curl_setopt($curl,CURLOPT_PROXYTYPE,CURLPROXY_SOCKS5);//使用了SOCKS5代理
        curl_setopt($curl, CURLOPT_PROXY, $httpProxy);
    }
    // 设置 cookies
    if ($cookies != "") {
        curl_setopt($curl, CURLOPT_COOKIE, $cookies);
    }
    $method = strtoupper($method);
    if ($method == 'POST') {
        curl_setopt($curl, CURLOPT_POST, true);
        if($request_header['Content-Type'] === 'application/x-www-form-urlencoded'){
            $payload = http_build_query($payload);
        }
        curl_setopt($curl, CURLOPT_POSTFIELDS, $payload);
    } else if ($method == 'PUT') {
        curl_setopt($curl, CURLOPT_CUSTOMREQUEST, 'PUT');
        curl_setopt($curl, CURLOPT_POSTFIELDS, $payload);
    } else if ($method == 'DELETE') {
        curl_setopt($curl, CURLOPT_CUSTOMREQUEST, 'DELETE');
        curl_setopt($curl, CURLOPT_POSTFIELDS, $payload);
    } else if ($method == 'PATCH') {
        curl_setopt($curl, CURLOPT_CUSTOMREQUEST, 'PATCH');
        curl_setopt($curl, CURLOPT_POSTFIELDS, $payload);
    } else if ($method == 'OPTIONS') {
        curl_setopt($curl, CURLOPT_CUSTOMREQUEST, 'OPTIONS');
        curl_setopt($curl, CURLOPT_POSTFIELDS, $payload);
    } else if ($method == 'HEAD') {
        curl_setopt($curl, CURLOPT_CUSTOMREQUEST, 'HEAD');
    } else {
        curl_setopt($curl, CURLOPT_HTTPGET, true);
    }
    //禁止验证对等证书
    curl_setopt($curl, CURLOPT_SSL_VERIFYPEER, false);
    //禁止验证主机证书
    curl_setopt($curl, CURLOPT_SSL_VERIFYHOST, false);
    curl_setopt($curl, CURLOPT_TIMEOUT, 20);
    curl_setopt($curl, CURLOPT_CONNECTTIMEOUT, 20);
    if ($request_header) {
        //追加请求头 配置curl内容
        curl_setopt($curl, CURLOPT_HTTPHEADER, array_map(function ($key, $value) {
            // echo "请求头：" . $key . ': ' . $value . "\n";
            return $key . ': ' . $value;
        }, array_keys($request_header), $request_header));
    }
    curl_setopt($curl, CURLOPT_HEADER, true);
    curl_setopt($curl, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($curl, CURLINFO_HEADER_OUT, true);
    curl_setopt($curl, CURLOPT_VERBOSE, true);
    //
    $response = curl_exec($curl);
    $header_size = curl_getinfo($curl, CURLINFO_HEADER_SIZE);
    $http_code   = curl_getinfo($curl, CURLINFO_HTTP_CODE);
    $body        = substr($response, $header_size);
    $header_str  = trim(substr($response, 0, $header_size));
    $header = array();
    $responseCookies = ''; // 新增一个字符串变量用于存储 cookies
    if ($header_str) {
        $header_arr  = explode("\r\n", $header_str);
        foreach ($header_arr as $every_header) {
            $header_temp = explode(': ', $every_header, 2);
            if (count($header_temp) == 2) {
                if (strtolower($header_temp[0]) == 'set-cookie') {
                    if ($responseCookies) {
                        $responseCookies .= '; '; // 如果已经有了一个 cookie，则在添加新的 cookie 前加上 "; "
                    }
                    $responseCookies .= $header_temp[1]; // 将 Set-Cookie 添加到 cookies 字符串中
                }
                $header[$header_temp[0]] = $header_temp[1];
            }
        }
    }

    if (curl_errno($curl)) {
        return ['status' => false, 'msg'  => curl_error($curl), 'data' => []];
    }
    curl_close($curl);

    return ['status' => true, 'msg'  => '', 'data' => ['http_code' => $http_code, 'body' => $body, 'header' => $header, 'cookies' => $responseCookies]];
}

function getCookie($cookieName, $cookieString)
{
    preg_match('/' . $cookieName . '=([^;]+)/', $cookieString, $matches);
    return $matches[1];
}
