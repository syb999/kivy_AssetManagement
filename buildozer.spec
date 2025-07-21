[app]
title = 资产管理工具

package.name = assetscanner

package.domain = org.example

source.dir = .

android.window_soft_input_mode = adjustResize

source.include_exts = py,png,jpg,kv,atlas,db,ttf,json

source.include_patterns = *.py, assets/*

source.include_dirs = assets, data

exclude_modules = os,json

version = 1.0

requirements = python3,kivy,pyjnius,jnius,plyer,sdl2,sdl2_image,sdl2_ttf,sdl2_mixer,android,pillow,sqlite3,numpy,pandas,openpyxl,et_xmlfile,requests


orientation = portrait

fullscreen = 0

android.permissions = CAMERA, INTERNET, READ_CLIPBOARD, ACCESS_NETWORK_STATE, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE

android.intent_filters = 
    android:mimeType="application/*" android:host="*/*"

android.manifest_application_arguments = 
    --meta-data android.hardware.camera.any=true
    --meta-data android.hardware.camera.autofocus=true

android.skip_patch = True

android.api = 30

android.minapi = 21

android.ndk_path = /home/oem/Android/Sdk/ndk/25.0.8775105

android.build_tools_version = 31.0.0

android.gradle_version = 7.5

android.python = 3.9

android.manifest.assets.include = assets/*

android.enable_androidx = True
android.use_androidx = True

android.arch = arm64-v8a

ios.kivy_ios_url = https://github.com/kivy/kivy-ios
ios.kivy_ios_branch = master

ios.ios_deploy_url = https://github.com/phonegap/ios-deploy
ios.ios_deploy_branch = 1.7.0

ios.codesign.allowed = false

[buildozer]
android.gradle_options = -Xmx2048m -XX:MaxPermSize=2048m

log_level = 2
