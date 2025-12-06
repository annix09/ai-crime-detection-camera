from ultralytics import YOLO
m = YOLO('best.pt')
print('class name:', m.names)