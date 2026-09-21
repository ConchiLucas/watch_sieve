"""Run after npm --prefix web run build; all HTTP requests use fixtures."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from watch_sieve.browser_fetch import _chrome_executable

root = Path(__file__).resolve().parents[1] / "web" / "dist"
state = {'busy': True, 'error': False, 'empty': False}
long_title = '这是一个用于验证中文长标题换行和移动端布局的标题，不能省略任何文字。' * 5
requests = []

def route_request(route):
    url = route.request.url
    requests.append((route.request.method, url))
    if '/api/filters' in url:
        route.fulfill(json={'sites': [{'id': 'v2ex', 'name': 'V2EX'}], 'categories': [{'id':'forum', 'name':'论坛'}]})
    elif '/api/topics' in url:
        if state['error']:
            route.fulfill(status=503, body='unavailable')
            return
        route.fulfill(json={'total': 0 if state['empty'] else 1, 'page':1, 'page_size':50, 'fetched_at':'2026-09-08T01:00:00Z', 'refreshing':state['busy'], 'failed_sites':['LINUX DO'], 'items': [] if state['empty'] else [{'title':long_title, 'url':'https://example.com/t/1', 'site_id':'v2ex', 'site_name':'V2EX', 'site_url':'https://example.com', 'category':'forum', 'category_label':'论坛', 'fetched_at':'2026-09-01T01:00:00Z'}]})
    elif '/api/classifications/catalog' in url:
        route.fulfill(json={
            'uncategorized': {'id': 'uncategorized', 'label': '未分类', 'count': 1},
            'groups': [{'id': 'ai', 'label': 'AI 用量', 'topics': [{'id': 'model-eval', 'label': '模型测评 / 降智', 'count': 1}]}],
        })
    elif '/api/classifications' in url:
        topic = 'uncategorized'
        if 'topic=' in url:
            topic = url.split('topic=', 1)[1].split('&')[0]
        label = '模型测评 / 降智' if topic == 'model-eval' else '未分类'
        route.fulfill(json={'topic_id': topic, 'topic_label': label, 'total': 1, 'page': 1, 'page_size': 50, 'items': [{'title': long_title, 'url': 'https://example.com/t/2', 'site_id': 'v2ex', 'site_name': 'V2EX', 'topic_id': topic, 'topic_label': label, 'fetched_at': '2026-09-01T01:00:00Z'}]})
    elif '/api/refresh' in url:
        route.fulfill(status=500, body='failed')
    elif '/api/watches/run' in url:
        route.fulfill(json={'ok':True,'model':'test-model','provider_id':'center','scanned':0,'kept':0,'skipped':0,'remaining':0,'message':'筛了 0 条'})
    elif '/api/watches/interests' in url:
        route.fulfill(json={'keywords':'秋招','revision':1})
    elif '/api/watches' in url:
        route.fulfill(json={'total':1,'page':1,'page_size':50,'keywords':'秋招','revision':1,'model':'aurora/auto','running':False,'items':[{'title':long_title,'url':'https://example.com/t/3','site_id':'v2ex','site_name':'V2EX','interest':'秋招','reason':'招聘','fetched_at':'2026-09-01T01:00:00Z'}]})
    else:
        relative = url.split('http://watch-sieve.test/', 1)[1] or 'index.html'
        path = root / relative
        if not path.exists() or path.suffix not in {'.js', '.css', '.html', '.map'}:
            path = root / 'index.html'
        route.fulfill(path=str(path), content_type='text/javascript' if path.suffix=='.js' else 'text/css' if path.suffix=='.css' else 'text/html')

with sync_playwright() as p:
    executable = _chrome_executable()
    browser = p.chromium.launch(headless=True, executable_path=str(executable) if executable else None)
    page = browser.new_page(viewport={'width':375,'height':900}, reduced_motion='reduce')
    page.route('**/*', route_request)
    page.goto('http://watch-sieve.test/')
    expect(page.locator('.menu a[aria-current="page"]')).to_have_text('标题')
    expect(page.locator('h1')).to_have_text('标题')
    expect(page.locator('.refresh')).to_have_text('刷新')
    expect(page.locator('.refresh')).to_be_enabled()
    expect(page.locator('.skeletons')).to_have_count(0)
    expect(page.locator('.topic')).to_have_text(long_title)
    input_box = page.locator('[name=q]')
    input_box.focus()
    input_box.fill('还没提交的中文筛选')
    input_box.dispatch_event('compositionstart', {'data':'中'})
    page.evaluate('window.originalInput = document.querySelector("[name=q]")')
    state['busy'] = False
    expect(page.locator('.refresh')).to_have_text('刷新', timeout=7000)
    expect(page.locator('.topic')).to_have_text(long_title)
    assert page.evaluate('window.originalInput === document.querySelector("[name=q]")')
    expect(input_box).to_have_value('还没提交的中文筛选')
    expect(input_box).to_be_focused()
    input_box.dispatch_event('compositionend', {'data':'中文'})
    expect(page.locator('.topic')).to_have_text(long_title)
    for width in [375,768,1440]:
        page.set_viewport_size({'width':width,'height':1000})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        assert page.locator('.topic').evaluate('(el) => getComputedStyle(el).textOverflow') != 'ellipsis'
        # Screenshots are optional; all assertions run without touching project data.
    page.evaluate('document.documentElement.style.zoom = "2"')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.evaluate('document.documentElement.style.zoom = "1"')
    state['error'] = True
    expect(page.locator('.fail')).to_contain_text('连接失败', timeout=7000)
    state['error'] = False
    state['empty'] = True
    expect(page.locator('.empty')).to_have_text('没有符合条件的标题', timeout=7000)
    page.locator('.refresh').click()
    expect(page.locator('.fail')).to_contain_text('刷新失败')
    assert len([r for r in requests if r[0]=='POST']) == 1
    expect(page.locator('.menu a', has_text='配置')).to_have_count(0)
    expect(page.locator('.menu a')).to_have_text(['标题', '分类', '关注'])
    page.locator('.menu a', has_text='分类').click()
    expect(page.locator('.menu a[aria-current="page"]')).to_have_text('分类')
    expect(page.locator('.refresh')).to_have_count(0)
    expect(page.locator('h1')).to_have_text('未分类', timeout=7000)
    expect(page.locator('.filters--class [name=q]')).to_have_count(1)
    expect(page.locator('.filters--class [name=category]')).to_have_count(0)
    expect(page.locator('.filters--class [name=date]')).to_have_count(0)
    expect(page.locator('th', has_text='主分类')).to_have_count(1)
    expect(page.locator('th', has_text='类型')).to_have_count(0)
    expect(page.locator('th', has_text='原文')).to_have_count(0)
    expect(page.locator('.side-list a', has_text='未分类')).to_have_count(1)
    page.locator('.side-list a', has_text='模型测评 / 降智').click()
    expect(page.locator('h1')).to_have_text('模型测评 / 降智', timeout=7000)
    expect(page.locator('.topic')).to_have_text(long_title)
    for width in [375, 768, 1440]:
        page.set_viewport_size({'width': width, 'height': 1000})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        assert page.locator('.topic').evaluate('(el) => getComputedStyle(el).textOverflow') != 'ellipsis'
    page.locator('.menu a', has_text='关注').click()
    expect(page.locator('.menu a[aria-current="page"]')).to_have_text('关注')
    expect(page.locator('h1')).to_have_text('关注', timeout=7000)
    expect(page.locator('.refresh')).to_have_text('筛选')
    expect(page.locator('#watch-filters [name=category]')).to_have_count(0)
    expect(page.locator('th', has_text='兴趣')).to_have_count(1)
    expect(page.locator('.topic')).to_have_text(long_title)
    for width in [375, 768, 1440]:
        page.set_viewport_size({'width': width, 'height': 1000})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        assert page.locator('.topic').evaluate('(el) => getComputedStyle(el).textOverflow') != 'ellipsis'
    page.locator('.menu a', has_text='标题').click()
    expect(page.locator('.menu a[aria-current="page"]')).to_have_text('标题')
    expect(page.locator('.refresh')).to_have_count(1)
    expect(page.locator('#filters [name=category]')).to_have_count(1)
    expect(page.locator('#filters [name=date]')).to_have_count(1)
    print('PASS: busy/completion, filter node & IME preservation, long Chinese title, 375/768/1440, 200% zoom, reduced motion, error/recovery, empty, failed POST; polling does not POST; no config menu; classification page independent filters and columns')
    browser.close()
