from flask import Flask, Response, render_template, stream_with_context, request
import cv2
import time
import paho.mqtt.client as mqtt
import threading
import os
import signal

app = Flask(__name__)

#Video crop size
x_size = y_size = 600

#Globalization variables
global doze, fall

#MQTT Broker address__Raspberry pi
broker_address = "192.168.137.165"

# Initialize camera
camera = cv2.VideoCapture(0)
camera.set(3, x_size)
camera.set(4, y_size)

class MQTTClient(threading.Thread):
    def __init__(self, broker_address):
        #Initialization
        super().__init__()
        self.client = mqtt.Client()
        self.client.connect(broker_address)
        self.message = "No data"
        self.running = True
        self.faces_count = 0
        self.eyes_count = 0
        self.stand_count = 0
        self.fall_90_count = 0
        self.fall_270_count = 0
        self.doze = 0
        self.fall = 0

    def run(self):
        #Publish MQTT message, Print status on consol
        while self.running:
            if self.message == 'Normal':
                msg = 'Normal'
            elif self.message == 'Doze off':
                msg = 'Doze off'
            elif self.message == 'Fall detect':
                msg = 'Fall detect'
            else:
                msg = 'Initialization'
            self.client.publish("hello", msg)          
            print(self.get_status())
            time.sleep(1)

    def update_message(self, message):
        self.message = message

    def update_counts(self, faces_count, eyes_count, stand_count, fall_90_count, fall_270_count, doze, fall):
        self.faces_count = faces_count
        self.eyes_count = eyes_count
        self.stand_count = stand_count
        self.fall_90_count = fall_90_count
        self.fall_270_count = fall_270_count
        self.doze = doze
        self.fall = fall

    def stop(self):
        self.running = False
        self.client.disconnect()

    def get_status(self):
        now = time.localtime()
        return f"{now.tm_year:04d}/{now.tm_mon:02d}/{now.tm_mday:02d} {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d} / Faces: {self.faces_count} / Eyes: {self.eyes_count} / Stand: {self.stand_count} / Fall_L: {self.fall_270_count} / Fall_R: {self.fall_90_count} / Status: {self.message} / Doze: {self.doze} / Fall: {self.fall}"

# Initialize MQTT
mqtt_client = MQTTClient(broker_address)
mqtt_client.start()

#Operating OpenCV
def generate_frames():
    global doze, fall
    doze = fall = last_warning_time = 0
    fullbody_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_fullbody.xml')
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')

    while camera.isOpened():
        _, image = camera.read()

# Make the image square by cropping
        height, width, _ = image.shape
        if height > width:
            margin = (height - width) // 2
            square_image = image[margin:margin + width, :]
        elif width > height:
            margin = (width - height) // 2
            square_image = image[:, margin:margin + height]
        else:
            square_image = image

# Make gray image, rotate image to detect fall        
        square_image = cv2.resize(square_image, (x_size, y_size))
        gray_image = cv2.cvtColor(square_image, cv2.COLOR_BGR2GRAY)
        cp = (square_image.shape[1] / 2, square_image.shape[0] / 2)
        rot_90 = cv2.getRotationMatrix2D(cp, 90, 1)
        rot_270 = cv2.getRotationMatrix2D(cp, 270, 1)       
        gray_image_rot_90 = cv2.warpAffine(gray_image, rot_90, (x_size, y_size))
        gray_image_rot_270 = cv2.warpAffine(gray_image, rot_270, (x_size, y_size))

# Detect faces and eyes
        faces = face_cascade.detectMultiScale(gray_image, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))
        eyes = []

        for (x, y, w, h) in faces:
            cv2.rectangle(square_image, (x, y), (x + w, y + h), (255, 0, 0), 2)
            face_gray = gray_image[y:y + h, x:x + w]
            face_color = square_image[y:y + h, x:x + w]
            eyes_detected = eye_cascade.detectMultiScale(face_gray, scaleFactor=1.1, minNeighbors=5)
            for (ex, ey, ew, eh) in eyes_detected:
                cv2.rectangle(face_color, (ex, ey), (ex + ew, ey + eh), (0, 255, 0), 2)
            eyes.extend(eyes_detected)

# Detect fall
        fullbody = fullbody_cascade.detectMultiScale(gray_image, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))
        fullbody_rot_90 = fullbody_cascade.detectMultiScale(gray_image_rot_90, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))
        fullbody_rot_270 = fullbody_cascade.detectMultiScale(gray_image_rot_270, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))

        for (x, y, w, h) in fullbody:
            cv2.rectangle(square_image, (x, y), (x + w, y + h), (255, 255, 0), 2)
        for (x1, y1, w1, h1) in fullbody_rot_90:
            cv2.rectangle(square_image, (y_size - y1 - h1, x1), (y_size - y1, x1 + w1), (0, 0, 255), 2)
        for (x2, y2, w2, h2) in fullbody_rot_270:
            cv2.rectangle(square_image, (y2, x_size - x2 - w2), (y2 + h2, x_size - x2), (0, 0, 255), 2)

# Fall, doze counter
        current_time = time.time()
        if (len(fullbody_rot_90) >= 1) or (len(fullbody_rot_270) >= 1):  
            if current_time - last_warning_time >= 1:
                mqtt_client.update_message('Fall detect')
                fall += 1  # fall 카운트 증가
                last_warning_time = current_time

        elif (len(eyes) - len(faces) * 2 < 0):        
             if current_time - last_warning_time >= 1:
                mqtt_client.update_message('Doze off')
                doze += 1  # doze 카운트 증가
                last_warning_time = current_time      
                 
        else:
            if current_time - last_warning_time >= 1:
                mqtt_client.update_message('Normal')
                last_warning_time = current_time

# Update status
        mqtt_client.update_counts(len(faces), len(eyes), len(fullbody), len(fullbody_rot_90), len(fullbody_rot_270), doze, fall)

# Encode video as image
        ret, buffer = cv2.imencode('.jpg', square_image)
        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    mqtt_client.stop()
    camera.release()

# HTML setting
@app.route('/')
def index():
    return render_template('index.html')

# Video(image) streaming
@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# Status streaming
@app.route('/status_feed')
def status_feed():
    def generate_status():
        while True:
            yield f"data: {mqtt_client.get_status()}\n\n"
            #time.sleep(1)

    return Response(stream_with_context(generate_status()), mimetype='text/event-stream')

# Doze counter reset button
@app.route('/reset_doze', methods=['POST'])
def reset_doze():
    global doze
    doze = 0
    return '', 204

# Fall counter reset button
@app.route('/reset_fall', methods=['POST'])
def reset_fall():
    global fall
    fall = 0
    return '', 204
    
# Program kill button
@app.route('/stop_script', methods=['POST'])
def stop_script():
    mqtt_client.stop()
    os.kill(os.getpid(), signal.SIGINT)
    return 'Server shutting down...', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
