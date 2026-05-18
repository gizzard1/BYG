### Comunicación con OpenAI. Se envía imagen con prompt y se recibe el json con la categoría del residuo. Se utiliza el modelo entrenado con Random Forest.

from openai import OpenAI
import json
import base64
import io
import re
from PIL import Image

import sys
import json


def normalizar_resultado(resultado):
    if not isinstance(resultado, dict):
        return {
            'is_garbage': False,
            'type': 'no_identified',
            'bonus': 0,
        }

    scores = resultado.get('scores') or resultado.get('type') or {}
    if not isinstance(scores, dict):
        scores = {}

    # Normalizar nombres por compatibilidad con el backend PHP
    mapping = {
        'organic': 'orgánico',
        'paper/cardboard': 'papel/cartón',
        'plastic_container/can': 'envase plástico/lata',
        'rejection': 'rechazo',
        'many_categories': 'many_categories',
        'no_identified': 'no_identified',
    }
    normalized_scores = {
        mapping.get(k, k): int(v) if isinstance(v, (int, float)) else 0
        for k, v in scores.items()
    }

    model_type = resultado.get('type')
    if isinstance(model_type, str) and model_type in mapping:
        final_type = mapping[model_type]
    else:
        final_type = max(normalized_scores, key=normalized_scores.get) if normalized_scores else 'no_identified'

    top_score = normalized_scores.get(final_type, 0)
    if final_type == 'no_identified' and normalized_scores:
        ranked = sorted(normalized_scores.items(), key=lambda x: x[1], reverse=True)
        if len(ranked) > 1 and ranked[0][1] <= 45 and ranked[1][1] >= 30:
            final_type = 'many_categories'
        elif len(ranked) > 1 and ranked[0][0] == 'no_identified' and ranked[1][1] >= 40:
            final_type = ranked[1][0]
            top_score = ranked[1][1]

    if final_type != 'no_identified' and top_score < 35:
        final_type = 'no_identified'

    return {
        'is_garbage': bool(resultado.get('is_garbage', True)),
        'type': final_type,
        'scores': normalized_scores,
        'bonus': int(resultado.get('bonus', 0) or 0),
    }


def predecir_categoria_residuo(imagen_base64, openai):
    # Crear el prompt para la imagen
    prompt = f"""Analyze the image and identify the waste object located on the white background area. Ignore the QR code and ignore anything outside the white-background waste area.

Return ONLY a valid JSON object with this structure:
{{
  "is_garbage": true,
  "type": "organic",
  "scores": {{
    "organic": 0,
    "paper/cardboard": 0,
    "plastic_container/can": 0,
    "rejection": 0,
    "many_categories": 0,
    "no_identified": 0
  }},
  "bonus": 0
}}

Rules:
- The values inside "scores" must be probabilities from 0 to 100.
- The sum of all probabilities in "scores" must be exactly 100.
- The field "type" must be the single best final class.
- Use visual evidence, not guesswork.
- "organic": food scraps, peels, fruit, vegetables, leftovers, natural decomposable matter.
- "paper/cardboard": sheet paper, carton, brown cardboard texture, folded box, paper fibers.
- "plastic_container/can": bottle, cap, plastic package, food container, aluminum can, metal/plastic industrial packaging.
- "rejection": dirty, contaminated, mixed with food/liquids, sanitary waste, non-recyclable state.
- "many_categories": two or more clearly visible waste types at the same time.
- "no_identified": only when the object is too ambiguous, occluded, blurred, or lacks enough evidence.
- Do not assign high probability to "plastic_container/can" unless there is clear visual evidence of a plastic or metal container.
- Do not use "plastic_container/can" as a default guess.
- If the object is ambiguous but one category is still visually more plausible, prefer that category with moderate confidence instead of defaulting to "no_identified".
- If multiple waste categories are clearly present, assign the highest probability to "many_categories".
- If the object is dirty, contaminated, or not recyclable, assign the highest probability to "rejection".
- If the object is not waste, set "is_garbage" to false, "type" to "no_identified", "scores" to null, and "bonus" to 0.
- Bonus must follow the most likely final category:
  - 80-100: easily recyclable and clean
  - 3-79: recyclable with treatment
  - 0-2: difficult or non-recyclable
- Be cautious but practical. Use "no_identified" only when evidence is genuinely insufficient.

Image: {imagen_base64}"""

    # Enviar la solicitud a OpenAI/DeepSeek
    response = openai.chat.completions.create(
        model="gpt-5.4-mini-2026-03-17",
        messages=[
            {
                'role': 'system',
                'content': (
                    "You are a waste-classification system. "
                    "Be careful, but do not overuse no_identified. "
                    "Choose the most visually supported category when there is reasonable evidence. "
                    "Return only valid JSON."
                )
            },
            {'role': 'user', 'content': prompt}
        ],
    )

    content = response.choices[0].message.content or "{}"

    # Si el modelo devuelve bloque markdown, extraer solo el JSON
    match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
    if match:
        content = match.group(1)

    return normalizar_resultado(json.loads(content))

def reducir_base64(base64_string, calidad=75, factor_escala=0.5):
    # Acepta tanto Base64 puro como data URI: data:image/jpeg;base64,...
    base64_string = re.sub(r'^data:image\/[a-zA-Z0-9.+-]+;base64,', '', base64_string)

    # 1. Decodificar Base64 a binario
    img_data = base64.b64decode(base64_string)
    img = Image.open(io.BytesIO(img_data))
    
    # 2. Redimensionar (opcional, pero recomendado)
    if img.mode in ('RGBA', 'LA'):
        background = Image.new(img.mode[:-1], img.size, '#ffffff')
        background.paste(img, img.split()[-1])
        img = background.convert('RGB')
        
    nuevo_ancho = int(img.size[0] * factor_escala)
    nuevo_alto = int(img.size[1] * factor_escala)
    img = img.resize((nuevo_ancho, nuevo_alto), Image.Resampling.LANCZOS)
    
    # 3. Comprimir y guardar en buffer
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=calidad, optimize=True)
    
    # 4. Volver a codificar a Base64
    new_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return new_base64

if __name__ == '__main__':
    try:
        data = json.load(sys.stdin)
  
        img64 = data['img64']
        openai_api_key = data.get('openai_api_key')

        if not openai_api_key:
            raise ValueError('No API key was provided. Please set OPENAI_API_KEY in Laravel environment.')

        openai = OpenAI(api_key=openai_api_key)

        newImage = reducir_base64(img64)
        response = predecir_categoria_residuo(newImage, openai)

        print(json.dumps(response, ensure_ascii=False))
    except Exception as e:
        print("ERROR:", str(e), file=sys.stderr)
        sys.exit(1)
  