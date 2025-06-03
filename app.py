from flask import Flask, request, jsonify, send_from_directory, send_file
from pymongo import MongoClient
from flask_cors import CORS
import datetime
import os
import pytz
import pandas as pd
from io import BytesIO
import requests

app = Flask(__name__)
CORS(app)

# =========================
# CONEXIÓN A MONGO
# =========================
client = MongoClient("mongodb+srv://carlosanmontero:P123456789@cluster0.i3xkixd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["sensoresDB"]
collection = db["lecturas"]

# =========================
# ENDPOINT PARA RECIBIR DATOS
# =========================
@app.route("/api/datos", methods=["POST"])
def recibir_datos():
    data = request.json
    if not data or not isinstance(data, dict):
        return jsonify({"error": "❌ JSON inválido"}), 400

    # 1. Guardar en MongoDB con timestamp
    data["timestamp"] = datetime.datetime.utcnow()
    collection.insert_one(data)

    # 2. Enviar a ESP32 SECUNDARIO con pantalla LCD
    try:
        payload = {
            "sensor1": round(data.get("t1", 0), 2),
            "sensor2": round(data.get("t2", 0), 2)
        }
        ESP_LCD_URL = "http://192.168.1.150/mostrar"  # Cambiar si la IP es diferente
        requests.post(ESP_LCD_URL, json=payload, timeout=1)
        print("✅ Reenviado a pantalla ESP32:", payload)
    except Exception as e:
        print("⚠️ No se pudo reenviar al ESP32 con LCD:", e)

    return jsonify({"mensaje": "✅ Datos guardados correctamente"}), 201

# =========================
# ENDPOINT PARA VER DATOS
# =========================
@app.route("/api/datos", methods=["GET"])
def obtener_datos():
    datos = list(collection.find({}, {"_id": 0}))
    return jsonify(datos)

# =========================
# DESCARGAR TODOS LOS DATOS EN EXCEL
# =========================
@app.route("/api/descargar", methods=["GET"])
def descargar_excel():
    datos = list(collection.find({}, {"_id": 0}))

    if not datos:
        return jsonify({"error": "No hay datos para exportar"}), 404

    for d in datos:
        utc = d["timestamp"].replace(tzinfo=pytz.utc)
        bogota = utc.astimezone(pytz.timezone("America/Bogota"))
        d["timestamp"] = bogota.strftime("%Y-%m-%d %H:%M:%S")

    df = pd.DataFrame(datos)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Lecturas", index=False)

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="datos_completos.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# =========================
# DESCARGA FILTRADA POR FECHA
# =========================
@app.route("/api/descargar/filtrado", methods=["GET"])
def descargar_excel_filtrado():
    fecha_inicio = request.args.get("inicio")
    fecha_fin = request.args.get("fin")

    if not fecha_inicio or not fecha_fin:
        return jsonify({"error": "Debes enviar parámetros 'inicio' y 'fin'"}), 400

    try:
        inicio = datetime.datetime.fromisoformat(fecha_inicio)
        fin = datetime.datetime.fromisoformat(fecha_fin)
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido"}), 400

    datos = list(collection.find({
        "timestamp": {
            "$gte": inicio,
            "$lte": fin
        }
    }, {"_id": 0}))

    if not datos:
        return jsonify({"error": "No hay datos en ese rango"}), 404

    for d in datos:
        utc = d["timestamp"].replace(tzinfo=pytz.utc)
        bogota = utc.astimezone(pytz.timezone("America/Bogota"))
        d["timestamp"] = bogota.strftime("%Y-%m-%d %H:%M:%S")

    df = pd.DataFrame(datos)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Lecturas", index=False)

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="lecturas_filtrado.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# =========================
# SERVIR FRONTEND
# =========================
@app.route("/")
def servir_index():
    return send_from_directory(os.path.join(os.path.dirname(__file__), '../frontend'), "index.html")

@app.route("/<path:archivo>")
def servir_estaticos(archivo):
    return send_from_directory(os.path.join(os.path.dirname(__file__), '../frontend'), archivo)

# =========================
# INICIAR SERVIDOR
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
