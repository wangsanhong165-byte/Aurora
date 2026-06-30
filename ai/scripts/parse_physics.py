import json

with open(r'C:\Users\LENOVO\Desktop\c++\ai\live2d-models\youxiaomiao\youxiaomiao.physics3.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print('=== Physics Settings ===')
for i, setting in enumerate(data.get('PhysicsSettings', [])):
    print(f'\nSetting {i}: id={setting.get("Id")}')
    for inp in setting.get('Input', []):
        print(f'  Input: {inp}')
    for output in setting.get('Output', []):
        print(f'  Output: {output}')
    vertices = setting.get('Vertices', [])
    print(f'  Vertices: {len(vertices)}')
    for j, v in enumerate(vertices):
        print(f'    Vertex {j}: position=({v.get("Position",{}).get("X")}, {v.get("Position",{}).get("Y")})')
        if 'Mobility' in v:
            print(f'      Mobility={v["Mobility"]}, Delay={v["Delay"]}, Acceleration={v["Acceleration"]}')