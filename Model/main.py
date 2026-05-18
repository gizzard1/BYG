### Comunicación con OpenAI. Se envía imagen con prompt y se recibe el json con la categoría del residuo. Se utiliza el modelo entrenado con Random Forest.

from openai import OpenAI
import os
import json
import base64
import io
from PIL import Image
import time


def predecir_categoria_residuo(imagen_base64,openai):
    # Crear el prompt para la imagen
    prompt = f"""Analiza la imagen y responde en JSON con los siguientes campos:

1. is_garbage (bool): Indica si el objeto es un residuo.
2. type (enum): Usa solo una de estas categorías:
   ["orgánico", "papel/cartón", "envase plástico/lata", "rechazo", "desconocido"]
3. bonus (number 1-100): Nivel de reciclabilidad:
   - 80-100: fácilmente reciclable y limpio
   - 3-79: reciclable con tratamiento
   - 0-2: difícil o no reciclable
4. contenedor (string): Usa el sistema de México:
   - verde: orgánicos
   - azul: papel/cartón
   - amarillo: plásticos/metales
   - gris: rechazo
5. msg (string): Describir anomalías si ves más de una categoría de residuos (many_categories) o si no se identifica (no_identified)

Reglas:
- Si el material está sucio o contaminado, clasifícalo como "rechazo".
- Si no puedes identificar el material con certeza, usa "desconocido" y contenedor "gris".
- "Rechazo" implica 0 puntaje en bonus.
- No agregues texto fuera del JSON.
- Si no es residuo, todo lo demás no es necesario calcularlo, puedes retornar nulos 
Imagen: {imagen_base64}"""

    # Enviar la solicitud a OpenAI
    response = openai.chat.completions.create(
        model="gpt-4.1-mini-2025-04-14",
        messages=[
            {'role': 'system', 'content': "Actúa como un experto en clasificación de residuos para una aplicación de reciclaje. Analiza la imagen proporcionada y responde solo con un JSON que contenga los campos especificados en el prompt. No agregues texto adicional fuera del JSON."},
            {'role': 'user', 'content': prompt}
        ]
    )

    # Obtener la categoría predicha del residuo
    json = response
    
    return json

def reducir_base64(base64_string, calidad=75, factor_escala=0.5):
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

img64 = ""
newImage = reducir_base64(img64,"openai_key")
response = predecir_categoria_residuo(newImage)
