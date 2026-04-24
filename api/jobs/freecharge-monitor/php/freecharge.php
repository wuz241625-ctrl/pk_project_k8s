<?php
require 'vendor/autoload.php';
include('Tool.php');

use Monolog\Logger;
use Monolog\Handler\RotatingFileHandler;
//log配置
# 将日志写入本地文件, 默认自动按 天 生成日志文件
global $log;
global $client;
global $tool;
$log = new Logger('freecharge_grab');
// $rotating_file_handler = new RotatingFileHandler('./freecharge_grab'.'.log', 7);
$rotating_file_handler = new RotatingFileHandler('./freecharge_grab_'.getmypid().'.log', 7);
$log->pushHandler($rotating_file_handler);

$tool = new Tool();
$time_grab = 10;
$order_time_out = 5*60;
$list_count = 5;

while (true){
    try{
        $client = new Predis\Client([
            'scheme' => 'tcp',
            'host'   => '127.0.0.1',
            'port'   => 6379,
        ]);

        //获取socks5代理ip
        $_proxies = get_socks_ip();
        if(!$_proxies){
            sleep(5);
            $log->error('login_freecharge 无代理ip，登出:');
            continue;
        }
        echo "start to pop".PHP_EOL;
        //获取需要登录或者爬取的id
        $login_freecharge = $client->lpop('login_freecharge');
//        var_dump($login_freecharge);
        if(!$login_freecharge){
            sleep(5);
            $log->error('login_freecharge 无pop:');
            continue;
        }
        echo "start working";
        $login_freecharge = json_decode($login_freecharge, true);
        if(!isset($login_freecharge['socks_ip']) || !$login_freecharge['socks_ip']){
            $login_freecharge['socks_ip'] = $_proxies[random_int(0, count($_proxies)-1)];
        }
        var_dump($login_freecharge);
        echo 'socks:' . $login_freecharge['socks_ip'];
        switch ($login_freecharge['status']){
            case 'sendOTP':
                // 超时10分钟，舍去
                if($login_freecharge['time'] < time() - $order_time_out){
                    $log->error('login_freecharge sendOTP超时，舍去，登出:'.json_encode($login_freecharge));
                    continue 2;
                }
                $OTP = sendOTP($login_freecharge, $login_freecharge['socks_ip']);
                if(!$OTP){
                    //第二次去获取otp
                    $OTP = sendOTP($login_freecharge, $login_freecharge['socks_ip']);
                    if(!$OTP){
                        $publish_data = [
                           'to'=>'freecharge',
                           'id'=>$login_freecharge['partner_id'],
                           'type'=>'freecharge.sendOTP',
                           'value'=>'',
                           'status'=>0
                        ];
                        //获取otp失败进行通知
                        $client->publish('phonepe_msg', json_encode($publish_data));
                        $log->error('login_freecharge 获取otp错误，登出:'.json_encode($login_freecharge));
                        continue 2;
                    }
                }
                $login_freecharge['status']= 'grabOTP';
                $client->rpush('login_freecharge', json_encode($login_freecharge));
                break;
            case 'grabOTP':
                $grabOTP = grabOTP($login_freecharge);
                if(!$grabOTP){
                    //还未获取otp, 检测时间是否超时，超时则丢弃
                    if($login_freecharge['time'] < time() - $order_time_out){
                        $log->error('login_freecharge 获取otp超时，登出:'.json_encode($login_freecharge));
                        continue 2;
                    }
                    //如果 login_phonepe list中元素过少，避免对redis连接数过多，限制时间
                    if($client->llen('login_phonepe') < $list_count){
                        sleep(2);
                    }
                    $client->rpush('login_freecharge', json_encode($login_freecharge));
                    break;
                }
                $log->info($login_freecharge['id'].' otp:' . $grabOTP);
                $login_freecharge['otp'] = $grabOTP;
                $login_if = login($login_freecharge);
                if(!$login_if){
                    //第二次去登录
                    $login_if = login($login_freecharge);
                    if(!$login_if){
                        $publish_data = [
                            'to'=>'freecharge',
                            'id'=>$login_freecharge['partner_id'],
                            'type'=>'freecharge.login',
                            'value'=>'',
                            'status'=>0
                        ];
                        //登录失败进行通知
                        $client->publish('phonepe_msg', json_encode($publish_data));
                        $log->error('login_freecharge 登录错误，登出:'.json_encode($login_freecharge));
                        continue 2;
                    }
                }
                var_dump('login:' . json_encode($login_freecharge));
                //登录成功进行通知
                $publish_data = [
                    'to'=>'freecharge',
                    'id'=>$login_freecharge['partner_id'],
                    'type'=>'freecharge.login',
                    'value'=>'',
                    'status'=>1
                ];
                $client->publish('phonepe_msg', json_encode($publish_data));
                $login_freecharge['status']= 'grabstatement';
                //10s才爬取一次
                if($login_freecharge['time'] < time() - $time_grab){
                    $grabstatement = grabstatement($login_freecharge);
                }
                if($grabstatement){
                    on_off($login_freecharge);
                }
                $client->rpush('login_freecharge', json_encode($login_freecharge));
                break;
            case 'grabstatement':
                # 添加判断在线的key
                $_key1 = 'login_on_freecharge_'.$login_freecharge['id'];
                $client->setex($_key1, 1*60 ,1);

                # 通知监控下线
                $_key2 = 'login_off_freecharge_'.$login_freecharge['id'];
                $login_off = $client->get($_key2);
                if($login_off) { // 180分钟之后才真正下线
                    if((int)$login_off + 180*60 < time()){
                        $client->del($_key2);
                        $log->error('login_freecharge 180分钟之后通知监控下线，登出:'.json_encode($login_freecharge));
                        continue 2;
                    }
                    //下线接单
                    on_off($login_freecharge, 0);
                }

                # 通知监控一键下线
                $_key3 = 'login_off_realtime_freecharge_'.$login_freecharge['id'];
                $login_off = $client->get($_key3);
                if($login_off) { // 直接下线
                    $client->del($_key1);
                    $client->del($_key2);
                    $client->del($_key3);
                    //下线接单
                    on_off($login_freecharge, 0);
                    $log->error('login_freecharge 通知监控一键下线，登出:'.json_encode($login_freecharge));
                    continue 2;
                }

                //10s才爬取一次
                if($login_freecharge['time'] < time() - $time_grab){
                    $grabstatement = grabstatement($login_freecharge);
                    if(!$grabstatement){
                        $login_freecharge['try_count'] += 1;
                    }
                    if($login_freecharge['try_count'] > 50){
                        //下线接单
                        on_off($login_freecharge, 0);
                        $log->error('login_freecharge try_count太多，登出:'.json_encode($login_freecharge));
                        continue 2;
                    }
                }
                //爬取upi失败次数过多
                if(isset($login_freecharge['upi_try']) && $login_freecharge['upi_try']>5){
                    //下线接单
                    on_off($login_freecharge, 0);
                    $log->error('login_freecharge upi_try太多，登出:'.json_encode($login_freecharge));
                    continue 2;
                }
                $login_off = $client->get($_key2);
                if(!$login_off && $grabstatement){
                    on_off($login_freecharge);
                }
                $client->rpush('login_freecharge', json_encode($login_freecharge));
                break;
            default:
                $log->error('login_freecharge 无状态: 登出'.json_encode($login_freecharge['id']));
                continue 2;
        }
    }catch(Exception $e)
    {
        $log->error($e->getMessage());
    }
}

//获取socks5代理ip
function get_socks_ip(){
    global $log;
    global $client;
    try{
        $_indian_socks_ip = $client->get('indian_socks_ip');
        if(!$_indian_socks_ip){
            $log->error('无 indian_socks_ip');
            return false;
        }
        $_indian_socks_ip = explode(',',$_indian_socks_ip);
        foreach ($_indian_socks_ip as $vs=> $v){
            if($v===''){
                unset($_indian_socks_ip[$vs]);
                continue;
            }
            $_indian_socks_ip[$vs] = trim($v);
        }
        return $_indian_socks_ip;
    }catch(Exception $e)
    {
        $log->error('login_freecharge 获取代理ip失败:'.$e->getMessage());
        return false;
    }
}

//sendOTP
function sendOTP(&$login_freecharge, $httpProxy){
    global $tool;
    global $log;
    try{
        $key_arr = $tool->getKey($httpProxy);
        $pke = $key_arr['data']['keys'][0]['key']; //
        $startTime = $key_arr['data']['keys'][0]['startTime'];
        $expiryTime = $key_arr['data']['keys'][0]['expiryTime'];
        if (empty($pke) || empty($startTime)) {
            $log->error('login_freecharge 获取pke失败:'. json_encode($login_freecharge). json_encode($key_arr));
            return false;
        }
        $log->info('login_freecharge 获取keys成功:'. json_encode($login_freecharge));

        $csrfId_arr = $tool->getCsrfId($httpProxy);
        $app_fc = $csrfId_arr["app_fc"];
        $csrfId = $csrfId_arr["csrfRequestIdentifier"]; //
        if (empty($app_fc) || empty($csrfId)) {
            $log->error('login_freecharge 获取csrfId失败:'. json_encode($login_freecharge). json_encode($key_arr));
            return false;
        }

        $cookies = "app_fc=" . $app_fc . ";_ga=GA1.1.590881904.1706179398;_ga_Q9NVXVJCL0=GS1.1.1706234979.2.0.1706234979.0.0.0; moe_uuid=693976e7-8977-445a-ac17-50fb5797098a";
        //登录验证码请求
        $phone = $login_freecharge['phone'];
        $code_str = $tool->loginCaptcha($phone, $cookies, $pke, $csrfId, $httpProxy);
        $code_json = json_decode($code_str, true);
        if ($code_json['data'] === null) {
//        $error_code = $code_json['error']['errorCode'];
//        $error_message = $code_json['error']['errorMessage'];
//        echo "验证码请求出错 :错误码:" . $error_code . ",错误信息: " . $error_message . "\n";
            $log->error('login_freecharge 获取验证码失败:'. json_encode($login_freecharge). json_encode($code_json));
            return false;
        }
        $optid = $code_json['data']['otpId'];
        $log->info('login_freecharge 验证码请求成功:'. $optid. json_encode($login_freecharge));
        $login_freecharge['otpid'] = $optid;
        $login_freecharge['cookies'] = $cookies;
        $login_freecharge['csrfId'] = $csrfId;
        return $optid;
    }catch(Exception $e)
    {
        $log->error($e->getMessage());
        return false;
    }
}

//grabOTP
function grabOTP($login_freecharge){
    global $tool;
    global $log;
    global $client;
    try{
        $_key = 'login_freecharge_OTP_'.$login_freecharge['id'];
        $otp = $client->get($_key);
        if(!$otp){
//            $log->error('login_freecharge 从redis中获取otp失败:'. json_encode($login_freecharge));
            return false;
        }
        return $otp;
    }catch(Exception $e)
    {
        $log->error($e->getMessage());
        return false;
    }
}

//login
function login(&$login_freecharge){
    global $tool;
    global $log;
    global $client;
    try{
        $res_arr = $tool->loginWithCode($login_freecharge['otpid'], $login_freecharge['otp'], $login_freecharge['cookies'], $login_freecharge['csrfId'], $login_freecharge['socks_ip']);
        $login_json = $res_arr["data"]["body"];
        $cookiesString =$res_arr["data"]["cookies"];
        $app_fc_ = getCookie("app_fc", $cookiesString);
        if (empty($app_fc_)) {
            $log->error('无法监听账单'. json_encode($login_freecharge));
            return false;
        }

        $cookies = "_ga=GA1.1.768328936.1706099429; moe_uuid=af80e942-62e3-45e7-b022-4527eb8ecaa2; _ga_Q9NVXVJCL0=GS1.1.1706099429.1.1.1706099537.0.0.0; app_fc=" . $app_fc_;
        var_dump('cookies:', $cookies);
        $login_freecharge['cookies'] = $cookies;
        return $cookies;
    }catch(Exception $e)
    {
        $log->error($e->getMessage());
        on_off($login_freecharge, 0);
        return false;
    }
}

//获取upi
function grabUpi(&$login_freecharge){
    global $tool;
    global $log;
    try{
        $res_str = $tool->getUpi($login_freecharge['cookies'], $login_freecharge['csrfId'], $login_freecharge['socks_ip']);
        if ($res_str['status'] == false) {
            $log->error('获取upi失败1：'. json_encode($res_str));
            return false;
        }
        $upi_json = $res_str["data"]["body"];
        $upi_arr = json_decode($upi_json, true);
        if (!$upi_arr['data'] || $upi_arr['result'] !== "Success"|| !$upi_arr['data']['vpas']) {
            $log->error('获取upi失败2：'. json_encode($res_str));
            return false;
        }
        $vpa ='';
        foreach ($upi_arr['data']['vpas'] as $v){
            if($v['status'] === 'PRIMARY'){
                $vpa = $v['vpa'];
            }
        }
        if(!$vpa){
            $log->error('获取upi失败3：'. json_encode($res_str));
            return false;
        }
        echo "获取upi成功：" . $vpa . "\n";
        $log->info($login_freecharge['id'].',获取upi成功：'. $vpa);
        $login_freecharge['upi'] = $vpa;
        return $vpa;
    }catch(Exception $e)
    {
        $log->error($e->getMessage());
        on_off($login_freecharge, 0);
        return false;
    }
}

//grabstatement
function grabstatement(&$login_freecharge){
    global $tool;
    global $log;
    global $client;

    try{
        $login_freecharge['time'] = time();
        //爬取upi
        if(!isset($login_freecharge['upi_time']) || $login_freecharge['upi_time'] + 5*60 < time()){
            $grabUpi = grabUpi($login_freecharge);
            if(!$grabUpi){
                $login_freecharge['upi_try'] = isset($login_freecharge['upi_try'])?$login_freecharge['upi_try'] + 1:1;
                $grabUpi = grabUpi($login_freecharge);
            }
            if(!$grabUpi){
                $login_freecharge['upi_try'] = isset($login_freecharge['upi_try'])?$login_freecharge['upi_try'] + 1:1;
                $log->error($login_freecharge['id'].",爬取upi失败1：次数：".$login_freecharge['upi_try'] . json_encode($login_freecharge));
                on_off($login_freecharge, 0);
                return false;
            }
            //发回upi,写入upi
            $orders_send = [
                'type'=>'UPI',
                'bank_name'=>'freecharge',
                'payment_id'=>$login_freecharge['id'],
                'partner_id'=>$login_freecharge['partner_id'],
                'upi'=>$grabUpi
            ];
            $if_send = send($orders_send);
            !$if_send && send($orders_send);
            if(!$if_send){
                on_off($login_freecharge, 0);
                $log->error($login_freecharge['id'].",爬取upi失败2：" . json_encode($orders_send));
                return false;
            }
            $log->info($login_freecharge['id'].",爬取upi成功：" . $grabUpi);
            $login_freecharge['upi_time'] = time();
            $login_freecharge['upi_try'] = 0;
        }

        //开始爬取账单
    //    $tool->listenPay($login_freecharge['cookies'], $httpProxy);
        $url = "https://www.freecharge.in/thv/moneydirection";
        $data = ["direction" => null];
        $dataString = json_encode($data);
        $res_arr = HttpGo::httpPost($url, $dataString, $login_freecharge['socks_ip'], $login_freecharge['cookies']);
        if(!$res_arr['status']){
            //解除接单集合
//            var_dump($res_arr);
            $log->info("爬取账单失败：".$login_freecharge['try_count'] . json_encode($res_arr));
            on_off($login_freecharge, 0);
            return false;
        }

        $res = $res_arr["data"]["body"];
        $log->info("爬取账单：". $login_freecharge['id']);
        $res_json = json_decode($res, true);
//        var_dump($res_json);
        //爬取账单为空
        // {"data":null,"error":{"errorCode":"ER-5100","errorMessage":"Login expired. Please login again.","errorSource":""}}    {"data":null,"error":{"errorCode":"ER-5100","errorMessage":"Transaction history doesn't exist","errorSource":""}}
        if(!$res_json['data'] && isset($res_json['error']) && $res_json['error'] && preg_match_all('/Transaction|history/', $res_json['error']['errorMessage'])){
            $log->info($login_freecharge['id'].":爬取账单为空：".$login_freecharge['try_count']. $res);
            //标定从账单为空转变为有数据时
            $login_freecharge['empty'] = 1;
            return true;
        }
        //爬取账单失败
        if(isset($res_json['error']) && $res_json['error']){
            //解除接单集合
            $log->info($login_freecharge['id'].":爬取账单失败：".$login_freecharge['try_count']. $res);
            on_off($login_freecharge, 0);
            return false;
        }
//        on_off($login_freecharge);
        //第一页账单
        $datas = [];
        foreach ($res_json['data'] as $v){
            if(!isset($login_freecharge['last_info']) || !$login_freecharge['last_info']){
                $login_freecharge['last_info'] = $v;
                $log->info("last_info-1：". $login_freecharge['id']. json_encode($v));
                if(isset($login_freecharge['empty']) && $login_freecharge['empty']){
                    $datas[] = $v;
                    unset($login_freecharge['empty']);
                }
                break;
            }
            if($login_freecharge['last_info'] == $v){
                break;
            }
            $datas[] = $v;
//            if($v['txnType'] === 'SEND_MONEY'){
//                $datas[] = $v;
//                break;
//            }
        }
        //开始回调
        if($datas){
            $login_freecharge['last_info'] = $datas[0];
            $log->info("last_info-2：". $login_freecharge['id']. json_encode($v));
            //        $datas = array_reverse($datas);
            foreach ($datas as $v){
    //            $login_freecharge['last_info'] = $v;
                if($v['txnStatus'] !== 'SUCCESS'){
                    $log->error($login_freecharge['id'].":账单not success：".json_encode($v));
                    continue;
                }
                $orders_send = [
                    'type'=>'New',
                    'bank_name'=>'freecharge',
                    'payment_id'=>$login_freecharge['id'],
                    'partner_id'=>$login_freecharge['partner_id'],
                    'amount'=>$v['txnAmount'],
                    'utr'=>$v['merchantOrderId'],
                    'timestamp'=>$v['timestamp'],

                    'trade_type'=>$v['txnType'],
                    'status'=>$v['txnStatus'],

                    'sourceVpa'=>$v['txnHistory']['upiinfo']['sourceVpa'],
                    'sourceName'=>$v['txnHistory']['upiinfo']['sourceName'],
                    'maskedAccnumber'=>$v['txnHistory']['upiinfo']['maskedAccnumber'],

                    'destName'=>$v['txnHistory']['upiinfo']['destName'],
                    'destVpa'=>$v['txnHistory']['upiinfo']['destVpa'],

                    'code'=>$v['txnHistory']['upiinfo']['remarks'],
                ];
                $if_send = send($orders_send);
                sleep(0.5);
                !$if_send && send($orders_send);
//                sleep(0.5);
//                $if_send && on_off($login_freecharge);
            }
        }
        return true;
    }catch(Exception $e)
    {
        $log->error($e->getMessage());
        on_off($login_freecharge, 0);
        return false;
    }
}

//send
function send($orders_send){
    global $tool;
    global $log;
    global $client;

    //开始发送回调信息
   $url = 'http://ospay689.com/api/order/Success';
//     $url = 'http://127.0.0.1:9000/order/Success';
    try{
        $res = HttpGo::httpPost($url, $orders_send, "", "", ['Content-Type'=> 'application/x-www-form-urlencoded']);
        $log->info('发送freecharge回调信息：' .json_encode($orders_send). '结果：'.json_encode($res['data']['body']));
        $_res = json_decode($res['data']['body'], true);
        var_dump($res['status'],$_res['code']);
        return $res['status'] && $_res['code'] == 100;
    }catch(Exception $e)
    {   $log->error('发送freecharge回调信息 出错：' .json_encode($orders_send));
        $log->error('发送freecharge回调信息 出错：'.$e->getMessage());
        return false;
    }
}

//online or offline
function on_off($login_freecharge, $_on = 1){
    global $tool;
    global $log;
    global $client;

    try{
        if($_on === 1){
            //放入接单集合
            $client->sadd('payment_online_ds', $login_freecharge['id']);
            $client->sadd('payment_online_df', $login_freecharge['id']);
            $client->lrem('payment_active_'.$login_freecharge['qr_channel'], 0, $login_freecharge['id']);
            $client->lpush('payment_active_'.$login_freecharge['qr_channel'], $login_freecharge['id']);
            if((int)$login_freecharge['qr_channel'] === 1002){
                $client->lrem('payment_active_1001', 0, $login_freecharge['id']);
                $client->lpush('payment_active_1001', $login_freecharge['id']);
            }
            $log->info('freecharge上线接单:'. $login_freecharge['id']);
            return true;
        }
        //解除接单集合
        $client->srem('payment_online_ds', $login_freecharge['id']);
        $client->srem('payment_online_df', $login_freecharge['id']);
        $client->lrem('payment_active_'.$login_freecharge['qr_channel'], 0, $login_freecharge['id']);
        $log->error('freecharge下线接单:'. $login_freecharge['id']);
    }catch(Exception $e)
    {
        $log->error($e->getMessage());
        return false;
    }
}