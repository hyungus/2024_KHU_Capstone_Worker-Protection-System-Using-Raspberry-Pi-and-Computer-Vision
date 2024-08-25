import paho.mqtt.client as mqtt
from gpiozero import LED
import pygame
import time

MQTT_SERVER = "192.168.137.106"
MQTT_TOPIC = "hello"

led = LED(21)
last_play_time = 0

# Initialize Pygame mixer
pygame.mixer.init()

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    global last_play_time
    current_time = time.time()
    print(f"Topic: {msg.topic}\nMessage: {msg.payload.decode()}")
    
    if msg.payload.decode() == "Normal":
        led.off()
        print("LED OFF")
        
    elif msg.payload.decode() == "Doze off":
        led.on()
        if current_time - last_play_time >= 1:
            # Update last play time before playing the sound
            last_play_time = current_time
            pygame.mixer.music.load('/home/kp/projects/fall/weye.mp3')
            pygame.mixer.music.play()
        print("LED ON")
        
    elif msg.payload.decode() == "Fall detect":
        led.on()
        if current_time - last_play_time >= 1.5:
            # Update last play time before playing the sound
            last_play_time = current_time
            pygame.mixer.music.load('/home/kp/projects/fall/wfall.mp3')
            pygame.mixer.music.play()
        print("LED ON")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect(MQTT_SERVER, 1883, 60)
    client.loop_forever()
except KeyboardInterrupt:
    print("Program interrupted")
    led.off()
    print("LED OFF")
