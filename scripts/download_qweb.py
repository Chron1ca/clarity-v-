import urllib.request
url = "https://raw.githubusercontent.com/qt/qtwebchannel/6.5/src/webchannel/qwebchannel.js"
urllib.request.urlretrieve(url, "src/clarity_v/settings/ui_web/lib/qwebchannel.js")
print("Downloaded qwebchannel.js")
