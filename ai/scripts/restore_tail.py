"""Quick script to restore the tail physics input section to original single ParamBreath input."""
import json

with open('live2d-models/youxiaomiao/youxiaomiao.physics3.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

tail = None
for s in data['PhysicsSettings']:
    if s['Id'] == 'PhysicsSetting47':
        tail = s
        break

if tail:
    tail['Input'] = [
        {
            "Source": {"Target": "Parameter", "Id": "ParamBreath"},
            "Weight": 100,
            "Type": "Angle",
            "Reflect": False
        }
    ]
    # Also reset vertex tuning to original
    tail['Vertices'] = [
        {"Position": {"X": 0, "Y": 0}, "Mobility": 1, "Delay": 1, "Acceleration": 0.9, "Radius": 0},
        {"Position": {"X": 0, "Y": 10}, "Mobility": 0.9, "Delay": 0.9, "Acceleration": 0.9, "Radius": 10},
        {"Position": {"X": 0, "Y": 20}, "Mobility": 0.83, "Delay": 0.85, "Acceleration": 0.9, "Radius": 10},
        {"Position": {"X": 0, "Y": 28}, "Mobility": 0.73, "Delay": 0.67, "Acceleration": 0.9, "Radius": 8},
        {"Position": {"X": 0, "Y": 36}, "Mobility": 0.7, "Delay": 0.67, "Acceleration": 0.9, "Radius": 8},
        {"Position": {"X": 0, "Y": 42}, "Mobility": 0.65, "Delay": 0.8, "Acceleration": 0.9, "Radius": 6}
    ]

with open('live2d-models/youxiaomiao/youxiaomiao.physics3.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write('\n')

print('Physics3.json restored to original inputs + original vertices')
# Verify
with open('live2d-models/youxiaomiao/youxiaomiao.physics3.json', 'r', encoding='utf-8') as f:
    data2 = json.load(f)
tail2 = None
for s in data2['PhysicsSettings']:
    if s['Id'] == 'PhysicsSetting47':
        tail2 = s
        break
if tail2:
    print(f'Inputs: {len(tail2["Input"])}')
    for inp in tail2['Input']:
        print(f'  {inp["Source"]["Id"]}: W={inp["Weight"]} T={inp["Type"]}')
    print(f'Vertices: {len(tail2["Vertices"])} entries')
    for v in tail2['Vertices']:
        print(f'  Y={v["Position"]["Y"]} M={v["Mobility"]} D={v["Delay"]} A={v["Acceleration"]}')