from __future__ import print_function, unicode_literals
import os
import sys
import time
import random
import json
import re
import shutil
from collections import defaultdict
from urllib.parse import quote
import requests
from lxml import etree
import fitz
from InquirerPy import prompt

# ============ 需要你修改的地方 ============
# 务必使用浏览器里最新的完整 Cookie
COOKIE = ''                         #Cookie
USER_AGENT = ''                     #用户信息
PAPERS_DIR = r'D:\papers'           #论文下载路径

def create_session():
    """创建一个携带登录 Cookie 的共享 Session"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
        'Referer': 'http://thesis.lib.sjtu.edu.cn/',
        'Cookie': COOKIE,
    })
    return session


def main():
    answers = search_arguments()
    info_url, pages = arguments_extract(answers)
    session = create_session()
    papers = download_main_info(info_url, pages, session)
    will_download = confirmation(papers)['confirmation']
    if will_download:
        paper_download(papers, session)
    else:
        print('Bye!')


def paper_download(papers, session):
    jpg_dir = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime()) + "".join(
        random.sample('zyxwvutsrqponmlkjihgfedcba23429837498234', 5))
    for paper in papers:
        print(100 * '@')
        paper_filename = paper['year'] + '_' + paper['filename'] + '_' + paper['author'] + '_' + paper['mentor'] + '.pdf'
        if verify_name(paper_filename):
            print("论文{}已经存在".format(paper_filename))
            continue
        print("正在下载论文：", paper['filename'])
        init(jpg_dir=jpg_dir)
        try:
            download_jpg(paper['link'], jpg_dir=jpg_dir, session=session)
            merge_pdf(paper_filename, jpg_dir=jpg_dir)
        except Exception as e:
            print("下载论文失败: {}".format(e))
        # 每篇论文之间稍作停顿，降低触发服务器限制的概率
        time.sleep(3)


def search_arguments():
    style_dict = {
        "separator": "#cc5454",
        "questionmark": "#673ab7 bold",
        "selected": "#cc5454",
        "pointer": "#673ab7 bold",
        "instruction": "",
        "answer": "#f44336 bold",
        "question": "",
    }

    questions = [
        {
            'type': 'list',
            'message': '请选择检索方式',
            'name': 'choose_key',
            'choices': ['主题', '题名', '关键词', '作者', '院系', '专业', '导师', '年份']
        },
        {
            'type': 'list',
            'message': '请选择检索硕士或博士论文',
            'name': 'xuewei',
            'choices': ['硕士', '博士', '硕士及博士']
        },
        {
            'type': 'list',
            'message': '请选择排序方式',
            'name': 'px',
            'choices': ['按题名字顺序排序', '按学位年度倒排序']
        },
        {
            'type': 'input',
            'name': 'content',
            'message': '请输入你的检索词'
        },
        {
            'type': 'input',
            'name': 'page',
            'message': '请输入想要检索的页面范围，一页20篇论文'
        }
    ]
    answers = prompt(questions, style=style_dict)
    return answers


def arguments_extract(answers):
    choose_key = {'主题': 'topic', '题名': 'title', '关键词': 'keyword', '作者': 'author',
                  '院系': 'department', '专业': 'subject', '导师': 'teacher', '年份': 'year'}
    xuewei = {'硕士及博士': '0', '博士': '1', '硕士': '2'}
    px = {'按题名字顺序排序': '1', '按学位年度倒排序': '2'}
    info_url = "http://thesis.lib.sjtu.edu.cn/sub.asp?content={}&choose_key={}&xuewei={}&px={}&page=".format(
        quote(answers['content']),
        choose_key[answers['choose_key']],
        xuewei[answers['xuewei']],
        px[answers['px']])
    print(info_url)
    pages = answers['page'].split('-')
    pages = [int(pages[0]), int(pages[1])]
    return info_url, pages


def confirmation(papers):
    print("\033[1;32m 检索到了以下{}篇文章\033[0m".format(len(papers)))
    for i in papers:
        print('\033[1;31m 题目\033[0m', i['filename'], '\033[1;34m 作者\033[0m', i['author'],
              '\033[1;36m 导师\033[0m', i['mentor'], '\033[1;35m 年份\033[0m', i['year'])
    questions = [
        {
            'type': 'confirm',
            'message': "确认下载{}篇文章吗？".format(len(papers)),
            'name': 'confirmation',
            'default': True
        }
    ]
    answers = prompt(questions)
    return answers


def verify_name(paper_filename):
    if not os.path.exists(PAPERS_DIR):
        os.makedirs(PAPERS_DIR)
    if paper_filename in os.listdir(PAPERS_DIR):
        return True
    return False


def init(jpg_dir):
    """初始化临时图片文件夹"""
    target = './{}/'.format(jpg_dir)
    if os.path.exists(target):
        try:
            shutil.rmtree(target)
            print("删除本地{}文件夹".format(jpg_dir))
        except Exception as e:
            print(e)
    try:
        os.mkdir(target)
        print("新建本地{}文件夹".format(jpg_dir))
    except Exception as e:
        print(e)


def download_main_info(info_url: str, pages: list, session: requests.Session):
    papers = []
    for page in range(pages[0], pages[1] + 1):
        print("正在抓取第{}页的info".format(page))
        info_url_construction = info_url + str(page)
        response = session.get(info_url_construction)

        print("状态码:", response.status_code)
        print("最终URL:", response.url)
        print("内容长度:", len(response.content))

        if 'sub.asp' not in response.url:
            print("警告：请求被重定向到非检索页面，Cookie 可能已失效")
            continue

        html = etree.HTML(response.content, etree.HTMLParser())
        if html is None:
            print("警告：HTML 解析失败")
            continue

        for i in range(2, 22):
            info_dict = defaultdict(str)
            try:
                filename = html.xpath('/html/body/section/div/div[3]/div[2]/table/tr[{}]//td[2]/text()'.format(i))[0]
                author = html.xpath('/html/body/section/div/div[3]/div[2]/table/tr[{}]/td[3]/div/text()'.format(i))[0]
                mentor = html.xpath('/html/body/section/div/div[3]/div[2]/table/tr[{}]/td[6]/div/text()'.format(i))[0]
                year = html.xpath('/html/body/section/div/div[3]/div[2]/table/tr[{}]/td[8]/div/text()'.format(i))[0]
                link = "http://thesis.lib.sjtu.edu.cn/" + html.xpath(
                    '/html/body/section/div/div[3]/div[2]/table/tr[{}]/td[9]/div/a[2]/@href'.format(i))[0]
                info_dict['filename'] = filename
                info_dict['author'] = author
                info_dict['mentor'] = mentor
                info_dict['year'] = year
                info_dict['link'] = link
                papers.append(info_dict)
            except Exception as e:
                print("第{}页第{}行解析失败: {}".format(page, i, e))
    print("总共抓取到{}个元数据信息".format(len(papers)))
    return papers


def download_jpg(url: str, jpg_dir: str, session: requests.Session):
    """
    下载逻辑：
    1. 请求论文链接，自动跟随重定向，最终到达 pdfindex.jsp 页面
    2. 从 pdfindex.jsp 的 HTML 源码中提取完整的图片路径（如 store/xxxx/P01_00001.jpg）
    3. 截取目录部分作为基础 URL，按序号循环下载图片
    """
    print("开始获取阅读页")
    resp = session.get(url, timeout=30)
    print("阅读页状态码:", resp.status_code)
    print("阅读页最终URL:", resp.url)

    if 'pdfindex.jsp' not in resp.url:
        print("警告：最终URL不是 pdfindex.jsp，可能被重定向到了其他页面")
        print("响应前500字节:", resp.content[:500])
        raise Exception("未能到达 pdfindex.jsp 阅读页")

    html_text = resp.text
    print("阅读页内容长度:", len(html_text))

    # 从 HTML 中提取完整的图片路径，例如 store/GZvGYC7VVR4eDrT3gAuH+A11/P01_00001.jpg
    match = re.search(r'store/[^"\']+/P\d+_00001\.jpg', html_text)
    if not match:
        # 兜底：尝试更宽松的匹配
        match = re.search(r'[^"\']*/P\d+_00001\.jpg', html_text)
    if not match:
        print("警告：未能从 HTML 中提取到图片路径，保存 HTML 供排查")
        with open('debug_pdfindex.html', 'w', encoding='utf-8') as f:
            f.write(html_text)
        raise Exception("未能提取图片路径，请查看 debug_pdfindex.html")

    full_path = match.group(0)
    print("提取到图片完整路径样例:", full_path)

    # 截取目录部分，例如 store/GZvGYC7VVR4eDrT3gAuH+A11
    dir_part = full_path.rsplit('/', 1)[0]
    base_url = "http://thesis.lib.sjtu.edu.cn:8443/read/" + dir_part + "/"
    print("图片基础URL:", base_url)

    i = 1
    fail_count = 0
    max_fail = 3
    saved_count = 0

    while True:
        fig_url = base_url + "P01_{:05d}.jpg".format(i)
        try:
            img_resp = session.get(fig_url, timeout=10)
            content = img_resp.content
            size = len(content)
        except Exception as e:
            print("请求第{}页失败: {}".format(i, e))
            fail_count += 1
            if fail_count >= max_fail:
                print("连续请求失败，退出下载")
                break
            i += 1
            continue

        if size < 2000:
            if size == 1049:
                print("第{}页返回资源不可用标志 (1049字节)，结束下载".format(i))
                break
            elif size == 746:
                print("第{}页返回错误占位图 (746字节)，连续失败{}/{}".format(i, fail_count + 1, max_fail))
                fail_count += 1
                if fail_count >= max_fail:
                    print("连续错误占位图过多，退出下载")
                    break
                i += 1
                continue
            else:
                print("第{}页大小异常: {} 字节 (连续失败{}/{})".format(i, size, fail_count + 1, max_fail))
                fail_count += 1
                if fail_count >= max_fail:
                    print("连续异常，结束下载")
                    break
                i += 1
                continue

        save_path = './{}/{}.jpg'.format(jpg_dir, i)
        with open(save_path, 'wb') as f:
            f.write(content)
        saved_count += 1
        print("正在采集第{}页 (大小: {} 字节) [已保存 {} 页]".format(i, size, saved_count))
        fail_count = 0
        i += 1

    print("下载完成，共保存 {} 页图片".format(saved_count))


def merge_pdf(paper_filename, jpg_dir):
    """将图片合并为 PDF"""
    img_dir = './{}/'.format(jpg_dir)
    if not os.path.exists(img_dir):
        print("图片目录 {} 不存在，跳过".format(img_dir))
        return

    img_files = [f for f in os.listdir(img_dir) if f.endswith('.jpg')]
    if len(img_files) < 1:
        print("论文 {} 没有下载到任何图片，跳过".format(paper_filename))
        shutil.rmtree(img_dir, ignore_errors=True)
        return

    img_files.sort(key=lambda x: int(x.split('.')[0]))

    doc = fitz.open()
    for img_file in img_files:
        img_path = os.path.join(img_dir, img_file)
        try:
            img = fitz.open(img_path)
            rect = img[0].rect
            page = doc.new_page(width=rect.width, height=rect.height)
            page.insert_image(rect, filename=img_path, keep_proportion=True, xref=0)
            img.close()
        except Exception as e:
            print("合并图片 {} 时出错: {}".format(img_file, e))
            continue

    if not os.path.exists(PAPERS_DIR):
        os.makedirs(PAPERS_DIR)
    pdf_path = os.path.join(PAPERS_DIR, paper_filename)
    doc.save(pdf_path)
    doc.close()
    print("已保存 PDF: {} (共 {} 页)".format(pdf_path, len(img_files)))

    shutil.rmtree(img_dir, ignore_errors=True)


if __name__ == '__main__':
    main()