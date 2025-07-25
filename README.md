#  库存管理系统-安卓

<div>

# 编译环境(linux mint-21.03):

sudo apt-get update

sudo apt-get install openjdk-17-jdk android-sdk sdkmanager autopoint default-jdk

再安装SDK cmdline-tools:

cd $HOME/Android/Sdk

wget https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip

unzip commandlinetools-linux-9477386_latest.zip

cp -r cmdline-tools tools

设置 ANDROID_SDK_ROOT 环境变量。编辑你的 ~/.bashrc 文件，添加以下行：

export ANDROID_SDK_ROOT=$HOME/Android/Sdk

export PATH=$PATH:$ANDROID_SDK_ROOT/tools:$ANDROID_SDK_ROOT/platform-tools

运行以下命令使环境生效：
source ~/.bashrc

使用 SDK Manager 安装所需的 SDK 组件和平台工具。运行以下命令启动 SDK Manager：

sdkmanager --install "platform-tools" "build-tools;latest" "platforms;android-31"

sdkmanager "build-tools;31.0.0"

sdkmanager "ndk;25.0.8775105"

-------------------------------------------------------------------------

导入路径:

echo 'export ANDROID_HOME=$HOME/Android/Sdk' >> ~/.bashrc

echo 'export PATH=$PATH:$ANDROID_HOME/emulator:$ANDROID_HOME/tools:$ANDROID_HOME/tools/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/build-tools/31.0.0' >> ~/.bashrc

echo 'export ANDROIDNDK=$HOME/Android/Sdk/ndk/25.0.8775105' >> ~/.bashrc

运行以下命令使环境生效：
source ~/.bashrc

接下来安装python3的相关依赖。主要使用kivy框架的buildozer来达成移植成安卓apk。

安装jnius解决访问 Android 的 Java API：

pip install pyjnius -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/

安装cython（3.x版本有bug，编译会报错）：

pip install cython==0.29.37 -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/

再安装主程序需要的依赖：

pip install kivy plyer buildozer pyandroid python-android -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/

注意修改buildozer.spec,修复（# Aidl not found, please install it.）路径识别问题（注意修改为自己的路径）:

android.ndk_path = /home/yourname/Android/Sdk/ndk/25.0.8775105

android.sdk_path = /home/yourname/Android/Sdk

android.build_tools_version = 31.0.0

打包生成的 APK 文件：

buildozer -v android debug

重构编译命令:

buildozer android clean

buildozer android debug

如果adb 已经连接了设备，则可以用下面的命令编译后直接运行程序：

buildozer android debug deploy run

--------------------------------------------------------------------------

为了使用ocr,推荐使用在线ocr:https://ocr.space/OCRAPI, 注册一个免费api后，每个月可以使用25000次。

--------------------------------------------------------------------------

当成功打包安卓app后，可以如此替换默认的图标和Loading页面：

把512x512分辨率的icon.png复制到当前项目的icons目录里并修改项目的buildozer.spec：

icon.filename = %(source.dir)s/icons/icon.png

把自定义的Loading页面presplash.png图片复制到当前项目的data目录里并修改项目的buildozer.spec：

presplash.filename = %(source.dir)s/data/presplash.png

android.presplash_delay = 0

android.presplash_scale_type = centerCrop


注意，有时buildozer编译报错是内存不足引起的，可以尝试修改buildozer.spec文件的底部，在[buildozer]下面添加：

android.gradle_options = -Xmx2048m -XX:MaxPermSize=1024m

--------------------------------------------------------------------------

如果遇到buildozer -v android debug编译时报错numpy版本问题时，可以尝试指定numpy版本：
pip install numpy==1.24.4
然后重新编译

</div>
