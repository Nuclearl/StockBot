from selenium import webdriver
from selenium.webdriver.firefox.options import Options
import time
from config import telemetr_password, telemetr_login


def get_image(txt):
    options = Options()
    options.add_argument('--headless')

    browser = webdriver.Firefox(options=options)

    browser.get("https://telemetr.me/")
    browser.find_element_by_id("btn_auth").click()
    browser.find_element_by_name("login[email]").send_keys(telemetr_login)
    browser.find_element_by_name("login[password]").send_keys(telemetr_password)
    browser.find_element_by_name("do_login").click()
    time.sleep(4)
    txt = txt.replace("https://t.me/", "")
    browser.get(f"https://telemetr.me/@{txt}")
    html = browser.page_source
    if "<title>Telemetr - 404</title>" in html:
        return "По данному каналу не найдет статистики"
    else:
        browser.find_element_by_xpath("/html/body/div[3]/div/div[2]/div[2]/div/div[22]/div/a").click()
        time.sleep(13)
        img = browser.find_element_by_xpath(
            "/html/body/div[3]/div/div[2]/div[2]/div/div[18]/div/div/div[2]/p[3]/img").get_attribute("src")
        return img
