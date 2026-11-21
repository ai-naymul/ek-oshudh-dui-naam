# Data sources and licences

| Source | What we use | Licence | Link |
|---|---|---|---|
| Medicine Dataset of Bangladesh (ArnobBot, MedEx-derived) | product registry, generics, drug classes, monographs, unit prices | MIT (as published on Hugging Face) | https://huggingface.co/datasets/ArnobBot/Medicine-Dataset-of-Bangladesh |
| Doctor's Handwritten Prescription BD dataset | handwritten medicine-name word images (evaluation + decision-model training pairs) | check before use (ODbL v1.0 per mirror metadata) | https://data.mendeley.com/datasets/zjjtptvn6f · mirror https://huggingface.co/datasets/lance-format/handwriting-ocr |
| RxHandBD | handwritten prescription word images (evaluation) | check before use | https://data.mendeley.com/datasets/dsb5r6vskg |
| Image-to-Text Bilingual Dataset from Medical Prescriptions | full handwritten prescriptions (line-level evaluation) | check before use | https://data.mendeley.com/datasets/tg2hm7n2bs |
| Online pharmacy product images | strip/box photos for the perception evaluation only (kept local, not redistributed) | publisher's terms; source URL recorded per image | `data/images_online/sources.csv` |

Raw files live in `data/raw/` and other gitignored folders. Download with `scripts/get_data.sh` and `scripts/get_handwriting.py`.
