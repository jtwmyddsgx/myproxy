# coding:utf-8
# 因为网络上的代理毕竟是有限的，所以希望大家不要滥用

import re
import requests
import time
import pymongo
import sys
from bs4 import BeautifulSoup
from multiprocessing.dummy import Pool

client = pymongo.MongoClient("localhost", 27017)
proxy = client['proxy']
proxy_pool = proxy['proxy_pool']
proxy_pool.ensure_index('ip_port', unique=True)  # 如果有重复的ip 写进去 会报错


class ProxyPool:  # 获取代理ip的类
    def get_soup(self, url):
        resp = requests.get(url)
        if resp.status_code == 200:
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "lxml")
            return soup

    def get_youdaili(self):
        soup = self.get_soup("http://www.youdaili.net/Daili/")
        a_tag = soup.select("div.newslist_body > ul > li > a")
        for i in a_tag:
            url = i.get('href')
            ip_re = re.compile(r'((\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\:\d{2,5})@([a-zA-Z0-9]{4,7}))')
            soup = self.get_soup(url)
            ips = ip_re.findall(soup.text)
            page_tag = soup.select("ul.pagelist > li > a")  # 是否还有第二页
            if page_tag:
                page = re.search(r"\d", page_tag[0].get_text()).group()
                page = int(page)
            else:
                page = 1
            if page >= 2:  # 如果有第二页就继续爬取
                for i in range(2, page + 1):
                    soup_sub = self.get_soup(url[:-5] + "_" + str(i) + ".html")
                    ips += ip_re.findall(soup_sub.text)
            if ips:
                for i in ips:
                    try: # 数据库不允许插入相同的ip，如果有相同的，这里将会报错，所以加个try
                        proxy_pool.insert_one({
                            'ip_port': i[1],
                            'protocol': i[2].lower(), # 协议
                            'update_time': int(time.time()) # 抓取时的时间
                        })
                    except pymongo.errors.DuplicateKeyError as ex:
                        pass
            print(url)


class ProxyCheck:

    def __init__(self):
        self.ip_port_all = [(i['ip_port'], i['protocol']) for i in proxy_pool.find()] # 查询，获取所有ip
    def remove_ip(self, ip_port): # 如果没能成功响应，将执行次方法，将其响应速度设置为空并且判断存在时间是否超过一周
        ip_data = proxy_pool.find({'ip_port': ip_port})
        proxy_pool.update_one({'ip_port': ip_port}, {'$set': {'speed': None}})
        if int(time.time()) - ip_data[0]['update_time'] > 604800:
            proxy_pool.remove({'ip_port': ip_port})

    def get_status(self, ip_port, protocol):
        url = "http://fz.58.com/"
        proxies = {"http": protocol + "://" + ip_port}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36",
        }
        time1 = time.clock()
        try: # 使用代理常常容易出错
            resp = requests.get(url, headers=headers, proxies=proxies, timeout=6)
        except requests.HttpError as ex:
            return self.remove_ip(ip_port)
        time2 = time.clock()
        time_result = time2 - time1 # 计算响应时间
        if resp.status_code == 200:
            print(ip_port)
            proxy_pool.update_one({"ip_port": ip_port},
                                  {'$set': {'speed': time_result, 'update_time': int(time.time())}})
        else:
            self.remove_ip(ip_port)

    def check(self): # 开启多线程进行检测
        pool = Pool(20)
        for i in self.ip_port_all:
            if i[1] == 'http':
                pool.apply_async(self.get_status, args=i)
        pool.close()
        pool.join()


if __name__ == "__main__":
    if len(sys.argv) > 1:  # 接收第一个参数，第一个参数为脚本运行的间隔时间
        time_sleep = int(sys.argv[1])
    else:
        time_sleep = 60 * 60
        
    while (True):
        pp = ProxyPool()
        pp.get_youdaili()
        pc = ProxyCheck()
        pc.check()
        time.sleep(time_sleep) #可以选择不要间隔
        
