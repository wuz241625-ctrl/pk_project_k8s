PHP写日志文件需要打开、写入和关闭文件等操作，PHP有fopen()，fwrite()和fclose()三个函数与之对应，而另一个函数file_put_contents()它也能字符串写入文件，其实这个函数实现了依次调用 fopen()，fwrite() 以及 fclose()。所以我们使用file_put_contents()非常简洁。值得注意的是，往文件后面追加内容时需要带上参数：FILE_APPEND。

实际运行中，我们有可能会遇到日志文件超大的情况，所以我们设置一个最大值，当日志文件大小超过这个最大值时，将此日志文件备份好，然后重新生成一个新的日志文件来记录新的日志内容。

在写日志前，我们将日志内容进行json格式化，所以需要将内容转化成JSON格式，然后写入文件。当然你也可以不用json，或者换作别的工具程序（如日志分析工具）可以阅读的格式。总之，我们写入的内容是方便必要时可以方便读取。
<?php
/* 
 * 日志类 
 * 每天生成一个日志文件，当文件超过指定大小则备份日志文件并重新生成新的日志文件 
*/
class Log {

    private $maxsize = 1024000; //最大文件大小1M 

    //写入日志 
    public function writeLog($filename,$msg)
    {
        $res = array();
        $res['msg'] = $msg;
        $res['logtime'] = date("Y-m-d H:i:s",time());

        //如果日志文件超过了指定大小则备份日志文件 
        if(file_exists($filename) && (abs(filesize($filename)) > $this->maxsize))
        {
            $newfilename = dirname($filename).'/'.time().'-'.basename($filename);
            rename($filename, $newfilename);
        }

        //如果是新建的日志文件，去掉内容中的第一个字符逗号 
        if(file_exists($filename) && abs(filesize($filename))>0)
        {
            $content = ",".json_encode($res);
        }
        else
        {
            $content = json_encode($res);
        }

        //往日志文件内容后面追加日志内容 
        file_put_contents($filename, $content, FILE_APPEND);
    }


    //读取日志 
    public function readLog($filename)
    {
        if(file_exists($filename))
        {
            $content = file_get_contents($filename);
            $json = json_decode('['.$content.']',true);
        }
        else
        {
            $json = '{"msg":"The file does not exist."}';
        }
        return $json;
    }
}

$filename = "logs/log_".date("Ymd",time()).".txt";
$msg = '写入了日志';
$Log = new Log(); //实例化 
$Log->writeLog($filename,$msg); //写入日志 
$loglist = $Log->readLog($filename); //读取日志 