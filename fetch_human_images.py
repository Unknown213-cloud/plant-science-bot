import os
import requests
import json
from PIL import Image

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://en.wikipedia.org/'
}

RAW_DIR = r"d:\insta bot\plant-science-bot\raw_human_batch"
os.makedirs(RAW_DIR, exist_ok=True)

# 20 distinct images across 4 human anatomy topics
IMAGES_PLAN = {
    "eye": [
        # Slide 1: Already generated 8k iris macro
        ("eye_01_iris", None, r"C:\Users\UMER COMPUTERS\.gemini\antigravity-ide\brain\63b1e22b-8b1b-4d86-b2c2-1c022403c959\eye_macro_hero_1792153716185.jpg"),
        # Slide 2: Already generated 3D cornea/lens
        ("eye_02_cornea_lens", None, r"C:\Users\UMER COMPUTERS\.gemini\antigravity-ide\brain\63b1e22b-8b1b-4d86-b2c2-1c022403c959\eye_lens_cornea_1792153740830.jpg"),
        # Slide 3: Retina photoreceptors
        ("eye_03_retina", "https://upload.wikimedia.org/wikipedia/commons/e/e8/1414_Rods_and_Cones.jpg", None),
        # Slide 4: Eye 3D structure & fovea
        ("eye_04_fovea", "https://upload.wikimedia.org/wikipedia/commons/thumb/7/76/3D_Medical_Animation_Eye_Structure.jpg/1280px-3D_Medical_Animation_Eye_Structure.jpg", None),
        # Slide 5: Optic nerve & eye blood vessels
        ("eye_05_optic_nerve", "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8f/Human_eye_with_blood_vessels.jpg/1280px-Human_eye_with_blood_vessels.jpg", None)
    ],
    "heart": [
        # Slide 1: 3D Anterior heart anatomy
        ("heart_01_anterior", "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1b/Heart_anterior_exterior_view.png/1024px-Heart_anterior_exterior_view.png", None),
        # Slide 2: Conduction system / SA node
        ("heart_02_conduction", "https://upload.wikimedia.org/wikipedia/commons/0/0f/Cardiac_Conduction_System.jpg", None),
        # Slide 3: Heart valves & chambers
        ("heart_03_valves", "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fe/Heart_near.png/1024px-Heart_near.png", None),
        # Slide 4: Coronary surface anatomy
        ("heart_04_coronary", "https://upload.wikimedia.org/wikipedia/commons/3/31/2005_Surface_Anatomy_of_the_Heart.jpg", None),
        # Slide 5: Myocardial striated muscle
        ("heart_05_myocardium", "https://upload.wikimedia.org/wikipedia/commons/thumb/4/46/Heart_diseccion.jpg/1024px-Heart_diseccion.jpg", None)
    ],
    "brain": [
        # Slide 1: Lateral cerebral cortex
        ("brain_01_cortex", "https://upload.wikimedia.org/wikipedia/commons/thumb/8/89/Brain_autopsy_lateral_view.jpg/1280px-Brain_autopsy_lateral_view.jpg", None),
        # Slide 2: Multipolar neuron anatomy
        ("brain_02_neuron", "https://upload.wikimedia.org/wikipedia/commons/thumb/1/10/Blausen_0657_MultipolarNeuron.png/1024px-Blausen_0657_MultipolarNeuron.png", None),
        # Slide 3: Synaptic junction & neurotransmitter release
        ("brain_03_synapse", "https://upload.wikimedia.org/wikipedia/commons/thumb/5/50/Synapse_figure.png/1024px-Synapse_figure.png", None),
        # Slide 4: Protective brain barriers & astrocytes
        ("brain_04_blood_brain_barrier", "https://upload.wikimedia.org/wikipedia/commons/b/b5/Protective_barriers_of_the_brain.jpg", None),
        # Slide 5: Motor & sensory connectome mapping
        ("brain_05_connectome", "https://upload.wikimedia.org/wikipedia/commons/thumb/b/bb/Blausen_0102_Brain_Motor%26Sensory_%28flipped%29.png/1280px-Blausen_0102_Brain_Motor%26Sensory_%28flipped%29.png", None)
    ],
    "lungs": [
        # Slide 1: 3D Detailed bronchial tree & lungs
        ("lungs_01_bronchial_tree", "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/Lungs_diagram_detailed.svg/1024px-Lungs_diagram_detailed.svg.png", None),
        # Slide 2: Alveoli & capillary bed (From previous raw alveoli generation)
        ("lungs_02_alveoli", None, r"C:\Users\UMER COMPUTERS\.gemini\antigravity-ide\brain\d0ad30f1-a6b4-4570-9410-7af392d2ebf4\raw_lung_alveoli_1792149478683.jpg"),
        # Slide 3: Bronchi & pulmonary lobes
        ("lungs_03_lobes", "https://upload.wikimedia.org/wikipedia/commons/thumb/d/db/Illu_bronchi_lungs.jpg/1024px-Illu_bronchi_lungs.jpg", None),
        # Slide 4: Thoracic thoracic CT scan & parenchyma
        ("lungs_04_parenchyma", "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/CT-Thorax-5.0-B70f-Lungs.jpg/1024px-CT-Thorax-5.0-B70f-Lungs.jpg", None),
        # Slide 5: Cardiopulmonary exchange system
        ("lungs_05_respiratory_system", "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e6/Heart-and-lungs.jpg/1024px-Heart-and-lungs.jpg", None)
    ]
}

downloaded = {}

for category, items in IMAGES_PLAN.items():
    print(f"\nProcessing {category.upper()} images...")
    downloaded[category] = []
    for name, url, local_file in items:
        out_file = os.path.join(RAW_DIR, f"{name}.png")
        if local_file and os.path.exists(local_file):
            print(f"  Using local file for {name}: {local_file}")
            im = Image.open(local_file)
            im.save(out_file)
            downloaded[category].append(out_file)
        elif url:
            print(f"  Downloading {name} from {url[:60]}...")
            try:
                r = requests.get(url, headers=HEADERS, timeout=15)
                if r.status_code == 200:
                    with open(out_file, "wb") as f:
                        f.write(r.content)
                    im = Image.open(out_file)
                    print(f"    Saved {out_file} (size: {im.size})")
                    downloaded[category].append(out_file)
                else:
                    print(f"    Failed ({r.status_code})")
            except Exception as e:
                print(f"    Error: {e}")

total = sum(len(v) for v in downloaded.values())
print(f"\nTotal ready raw images: {total} / 20")
