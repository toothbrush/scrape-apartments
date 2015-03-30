#!/usr/bin/env python
# -%- coding: utf-8 -%-

from __future__ import unicode_literals
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
)

import urlparse
import re
import os
import datetime
import pprint
import json
import traceback
import requests
import time
import sys
import codecs
sys.stdout = codecs.getwriter('utf8')(sys.stdout)

class LOGIN:
    password = '' #your password on Ebay small ads
    email = '' #your email on Ebay small ads

#Replace this by the search you're intersted in (do a manual search and copy/paste URL)
search_url = 'http://kleinanzeigen.ebay.de/anzeigen/s-wohnung-mieten/berlin/anbieter:privat/anzeige:angebote/c203l3331+wohnung_mieten.zimmer_i:2,3'
slack_url = None #if you have Slack, put a Webhook URL here and you will get notified if the bot finds something interesting.

#Here we will keep ads that we have visited already...
db_filename = 'ads.json'

def send_slack_message(text):
    payload = {'text' : text,'mrkdwn' : True}
    if slack_url is None:
        return
    try:
        response = requests.post(slack_url,data = {'payload' : json.dumps(payload)})
    except:
        print "Can't deliver message to Slack!"

def load_db():
    ads = []
    if not os.path.exists(db_filename):
        return []
    with open(db_filename,"r") as input_file:
        for line in input_file:
            ads.append(json.loads(line))
    return ads

def save_db(ads):
    with open(db_filename,"w") as output_file:
        for ad in ads:
            try:
                output_file.write(json.dumps(ad)+"\n")
            except:
                print "Could not write entry!"
                continue

def is_suitable(ad):
    """
    This function determines if an ad is suitable or not. Modify according to your needs.
    """
    if not 'Ort' in ad or not 'Zimmer' in ad or not 'rent' in ad or not 'Quadratmeter' in ad:
        return False
    if ad['rent'] is not None:
        try:
            rent = int(ad['rent'])
            if rent > 550 or rent < 300:
                return False
        except:
            return None
    else:
        return False
    try:
        if int(ad['Zimmer']) < 2 or int(ad['Zimmer']) > 3:
            return False
    except:
        return None
    try:
        if int(ad['Quadratmeter']) < 50 or int(ad['Quadratmeter']) > 90:
            return False
    except:
        return None
    exchange_regex = r"möbliert|alleinerziehende|Zwischenmiete|WBS|Wohnberechtigungsschein|Wohnungstausch|Tauschangebot|Tausch"
    if re.search(exchange_regex,ad['description'],re.I) or \
       re.search(exchange_regex,ad['title'],re.I):
        return False
    if re.search(r"suche|sucht",ad['title'],re.I):
        return False
    if not re.search(ur'Wedding|Moabit|Mitte|Neuk[^\s]+lln|Tiergarten|Sch[^\s]+neberg|Treptow|Wilmersdorf|Tegel|Tempelhof|Charlottenburg|Friedrichshain|Prenzlauer\s+Berg|Steglitz|Friednau',ad['Ort'],re.I):
        return False
    no_go_zones = ur"Lichenrade|Lankwitz|Schmargendorf|Treptow|Karlshorst|Lichterfelde|Britz|Mariendorf"
    if re.search(no_go_zones,ad['Ort'],re.I) or re.search(no_go_zones,ad['title'],re.I) or re.search(no_go_zones,ad['description'],re.I):
        return False
    return True

def notify_me_of(ad):
    my_ad = {}
    my_ad.update(ad)
    my_ad['description'] = "> "+ "\n> ".join(my_ad['description'].split("\n"))
    message =u"""
## Neues Angebot: %(title)s

%(url)s

Zimmer: **%(Zimmer)s**
Miete: **%(rent_str)s**
Ort: **%(Ort)s**

## Beschreibung

%(description)s

## Telefon

**%(phone)s**

""" % my_ad

    print message

    send_slack_message(message)

#Modify according to your needs ;)
contact_message =u"""Hallo,

Ihre Anzeige klingt wirklich interessant! Ich bin auf der Suche nach einer 2/3-Zimmer Wohnung in Berlin, das Angebot passt da genau. [...]

Falls ich auf Ihr Suchprofil passe würde ich mich sehr freuen, falls wir kurz telefonieren könnten um zu schauen, ob die Rahmenbedingungen stimmen und eventuell einen Besichtigungstermin zu vereinbaren. [...]

Alle benötigten Unterlagen (Schufa, Einkommensnachweise, 
Mietschuldenfreiheit, Selbstauskunft, ...) für die Anmietung habe ich bereits vorliegen.

Freue mich sehr über Ihre kurze Rückmeldung!

Viele Grüße
[your name]
"""

lines = contact_message.split(u"\n")
contact_message = u""

for line in lines:
    if not line.strip():
        contact_message+=u"\n\n"
    else:
        contact_message+=unicode(line.strip())+u" "

print contact_message

import time

last_ping = None

def contact(ad,browser):

    ad['contacted'] = True

    watchlist_element = browser.find_element_by_id('viewad-action-watchlist')
    if re.search(ur"hinzufügen",watchlist_element.text) is None:
        print "Has already been added to watchlist, skipping..."
        return
    else:
        print "Adding to watchlist"
        browser.find_element_by_id("viewad-lnk-watchlist").click()
        time.sleep(5)

    form = browser.find_element_by_id('viewad-contact-bottom-form')
    submit_button = browser.find_element_by_id('viewad-contact-bottom-submit')
    message_element = browser.find_element_by_id('viewad-contact-bottom-message')
    message_element.send_keys(contact_message)
    submit_button.click()
    send_slack_message("**Angeschrieben**: %s (%s)" % (ad['title'],ad['url']))
    time.sleep(5)


def get_attributes(browser):
    attribute_lists = browser.find_elements_by_xpath('//dl[contains(@class,"a-medium-width attributelist")]')
    attributes = {}
    for attribute_list in attribute_lists:
        current_name = None
        for item in attribute_list.find_elements_by_xpath('.//dd | .//dt'):
            if item.tag_name == 'dt':
                current_name = item.text.strip()
                if not current_name:
                    continue
                if current_name[-1] == ':':
                    current_name = current_name[:-1]
            elif current_name is not None:
                attributes[current_name] = item.text.strip()

    rent_str = browser.find_element_by_id('viewad-price').text

    attributes['rent_str'] = rent_str

    try:
        attributes['rent'] = re.match(r".*?(\d+)\s*EUR",rent_str).group(1)
    except:
        attributes['rent'] = None

    attributes['title'] = browser.find_element_by_id('viewad-title').text

    phone_number = browser.find_elements_by_xpath('//*[contains(@class,"phoneline-number")]')

    if len(phone_number):
        attributes['phone'] = phone_number[0].text
    else:
        attributes['phone'] = ''

    p_text = browser.find_element_by_id('viewad-description-text')
    attributes['description'] = p_text.text

    return attributes

def check_ads(ads_by_id):

    browser = webdriver.Firefox()
    browser.set_page_load_timeout(60)
    try:
        browser.delete_all_cookies()

        if True:
            browser.get('http://kleinanzeigen.ebay.de/')
            login_field = browser.find_element_by_xpath("//*[contains(text(), 'Einloggen')]")
            login_field.click()
            browser.find_element_by_id('login-email').send_keys(LOGIN.email)
            browser.find_element_by_id('login-password').send_keys(LOGIN.password)
            browser.find_element_by_id('login-submit').click()

        browser.get(search_url)

        result_list = browser.find_element_by_id('srchrslt-adtable')
        result_items = result_list.find_elements_by_xpath(".//li")

        links = {}

        for result_item in result_items:
            link = result_item.find_element_by_xpath('.//a[contains(@class, "ad-title")]')
            links[link.get_attribute('href')] = link.text

        try:
            for link_href,link_text in links.items():
                o = urlparse.urlparse(link_href)
                ad_number = re.match(r".*\/([\d\w\-]+)$",o.path)
                if not ad_number:
                    print "Cannot find ad number"
                    continue
                ad_id = ad_number.group(1)
                print ad_id
                browser.get(link_href)

                try:
                    element = WebDriverWait(browser, 10).until(
                            EC.presence_of_element_located((By.ID, "viewad-action-watchlist"))
                        )
                    print "Found it"
                except TimeoutException: 
                    print "Timeout!"
                    continue

                attributes = get_attributes(browser)

                attributes['id'] = ad_id
                attributes['url'] = link_href

                if not 'Anzeigennummer' in attributes:
                    print "No AD ID found..."
                    continue

                ad_number = attributes['Anzeigennummer']

                new_ad = False
                if ad_number in ads_by_id:
                    print "Updating ad."
                    ads_by_id[ad_number].update(attributes)
                else:
                    print "New ad!"
                    new_ad = True
                    ads_by_id[ad_number] = attributes
                print "Suitable:",is_suitable(ads_by_id[ad_number])
                if not new_ad:
                    continue

                ad = ads_by_id[ad_number]
                ad['suitable'] = is_suitable(ad)

                if ad['suitable']:
                    if 'contacted' not in ad or ad['contacted'] == False:
                        print "Not yet contacted!"
                        if not ad['phone']:
                            contact(ad,browser)
                        else:
                            send_slack_message("Bitte selbst anrufen: %s (%s - %s)" % (ad['phone'],ad['title'],ad['url']) )
                        notify_me_of(ad)
                else:
                    send_slack_message("Nicht geeignet: %s (%s)" % (ad['title'],ad['url']))
                pprint.pprint(ads_by_id[ad_number])

                print "\n\n\n"


        except KeyboardInterrupt:
            print "CTRL-C pressed, aborting..."
            raise
    finally:
        browser.quit()

if __name__ == '__main__':

    ads = load_db()

    print "Loaded %d entries" % len(ads)

    ads_by_id = {}

    for ad in ads:
        if 'Anzeigennummer' in ad:
            ads_by_id[ad['Anzeigennummer']] = ad

    while True:
        if last_ping is None or time.time()-last_ping > 60*60:
            last_ping = time.time()
            send_slack_message("Indexed %d ads so far, found %d suitable ones." % (len(ads_by_id),len([ad for ad in ads_by_id.values() if 'suitable' in ad and ad['suitable']])))
        try:
            check_ads(ads_by_id)
        except KeyboardInterrupt:
            save_db(ads_by_id.values())
            break
        except:
            print "An exception occured..."
            print traceback.format_exc()
            send_slack_message("Exception: %s" % traceback.format_exc())
        print "Waiting 30 secs..."
        save_db(ads_by_id.values())
        time.sleep(30)
