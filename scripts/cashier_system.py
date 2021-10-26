#!/usr/bin/env python
# -*- coding: utf-8 -*-


# 必要なライブラリをインポート
import rospy
import cv2
import subprocess
import roslib.packages
import boto3
import wave
import csv
from cv_bridge import CvBridge
from sensor_msgs.msg import Image
import sys
reload(sys)
sys.setdefaultencoding("utf-8")


class CashierSystem(object):
    def __init__(self):
        rospy.Subscriber("/image_raw", Image, self.imageCB)
        self.image = None
        self.enable_process = 0
        self.pkg_path = roslib.packages.get_pkg_dir("cashier_system")
        self.goukei = 0

        # CSVを読み込んでデータベースを作成
        self.dictionary = {}
        with open(self.pkg_path + "/scripts/database.csv", "r") as f:
            for i, row in enumerate(csv.reader(f)):
                if i == 0:
                    continue
                if len(row) > 0:
                    self.dictionary[row[0]] = row[1]

    def process(self):
        # -------------------------------
        # カメラ画像を保存する
        # -------------------------------
        target_file = self.pkg_path + "/scripts/camera.jpg"
        cv2.imwrite(target_file, self.image)
        image = cv2.imread(target_file)
        
        # -------------------------------
        # 画像認識してデータベースと比較する
        # -------------------------------
        detect_data = self.detectLabels(target_file)
        items = []
        for d in detect_data:
            if d["Name"] in self.dictionary:
                items.append((d["Name"], self.dictionary[d["Name"]]))
        if len(items) == 0:
            print("商品が見つかりませんでした。スタッフを呼んでください。")
            print("=======================================================================")
            # 案内文を音声合成して再生
            speech_filepath = self.synthesizeSpeech("商品が見つかりませんでした。スタッフを呼んでください。")
            subprocess.check_call('aplay --quiet -D plughw:0 {}'.format(speech_filepath), shell=True)
        else:
            name = self.transrate(items[0][0])
            # 案内文を音声合成
            speech_filepath = self.synthesizeSpeech(name + "がスキャンされました。価格は" + items[0][1] + "円です。")
            # 合計金額を計算
            self.goukei += int(items[0][1])
            print("スキャンされた商品: {}(¥{})".format(name, items[0][1].decode('utf-8')))
            # 案内文の音声を再生
            subprocess.check_call('aplay --quiet -D plughw:0 {}'.format(speech_filepath), shell=True)
            # 案内用のメッセージを表示
            self.infomessage()
            

    def detectLabels(self, path):
        # AWSで画像認識
        rekognition = boto3.client("rekognition")
        with open(path, 'rb') as f:
            return rekognition.detect_labels(
                Image={'Bytes': f.read()},
            )["Labels"]
        return []


    def transrate(self, text):
        # AWSで翻訳
        translate = boto3.client(service_name="translate")
        return translate.translate_text(
            Text=text,
            SourceLanguageCode="en",
            TargetLanguageCode="ja"
        )["TranslatedText"]


    def synthesizeSpeech(self, text):
        # AWSで音声合成
        polly = boto3.client(service_name="polly")
        speech_data = polly.synthesize_speech(
            Text=text,
            OutputFormat='pcm',
            VoiceId='Mizuki'
        )['AudioStream']
        filename = self.pkg_path + "/scripts/speech.wav"
        wave_data = wave.open(filename, 'wb')
        wave_data.setnchannels(1)
        wave_data.setsampwidth(2)
        wave_data.setframerate(16000)
        wave_data.writeframes(speech_data.read())
        wave_data.close()
        return filename

    def okaikei(self):
        print("お会計は¥{}です。".format(self.goukei))
        print("お支払いは不要です。ご利用ありがとうございました！")
        print("=======================================================================")
        print("３秒後にプログラムを終了します。")
        rospy.sleep(3)
        sys.exit(0)


    def imageCB(self, msg):
        # カメラ画像を受け取る
        self.image = CvBridge().imgmsg_to_cv2(msg, "bgr8")
        cv2.imshow('Camera', cv2.resize(self.image, dsize=None, fx=0.75, fy=0.75))
        # キー判定をする
        key = cv2.waitKey(1)
        if key == ord('s'):
            self.enable_process = 1
        if key == ord('e'):
            self.enable_process = 2

    def infomessage(self):
        print("=======================================================================")
        print("無人レジシステム")
        print("  - カメラウィンドウを選択した状態で[s]キーを押すと商品スキャン")
        print("  - お会計は[e]キー")
        print("=======================================================================")

    def run(self):
        # 案内用のメッセージを表示
        self.infomessage()
        rate = rospy.Rate(10)
        while not rospy.is_shutdown():
            if self.enable_process == 1:
                self.enable_process = 0
                self.process()
            if self.enable_process == 2:
                self.enable_process = 0
                self.okaikei()
            rate.sleep()

if __name__ == '__main__':
    # ノードを宣言
    rospy.init_node('cashier_system_node')
    CashierSystem().run()
