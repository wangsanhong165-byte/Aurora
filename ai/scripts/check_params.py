import json

d = json.load(open(r'C:\Users\LENOVO\Desktop\c++\ai\live2d-models\youxiaomiao\youxiaomiao.model3.json', 'r', encoding='utf-8'))
params = d.get('Parameters', [])
print(f'Total parameters: {len(params)}')

# Find ParamBreath and tail-related params
for i, p in enumerate(params):
    name = p.get('Name', '')
    pid = p.get('Id', '')
    if 'Breath' in name or 'breath' in pid or 'Rotation' in name or 'ArtMesh' in name or '212' in pid:
        print(f'  [{i}] Name="{name}" Id="{pid}"')