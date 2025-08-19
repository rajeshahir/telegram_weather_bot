#!/usr/bin/env python3
import os, logging, requests, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime
from functools import reduce
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

AVAILABLE_MODELS = {
    "GFS": "gfs_seamless",
    "ICON": "icon_seamless",
    "ECMWF": "ecmwf_ifs025",
    "JMA": "jma_seamless",
    "GEM": "gem_seamless",
    "UKMO": "ukmo_seamless",
    "MeteoFrance": "meteofrance_seamless",
    "ACCESS-G": "bom_access_global"
}

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

def fetch_model(lat, lon, tz, model_key):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {"latitude": lat, "longitude": lon,
              "hourly": "temperature_2m,precipitation,wind_speed_10m",
              "timezone": tz, "models": model_key}
    r = requests.get(url, params=params, timeout=30); r.raise_for_status()
    j = r.json()
    return pd.DataFrame({"time": pd.to_datetime(j["hourly"]["time"]),
                         "temp": j["hourly"]["temperature_2m"],
                         "precip": j["hourly"]["precipitation"],
                         "wind": j["hourly"]["wind_speed_10m"]})

def build_forecast(lat, lon, tz, date_str, start, end, models):
    dfs = []
    for m in models:
        df = fetch_model(lat, lon, tz, AVAILABLE_MODELS[m])
        df = df[df["time"].dt.strftime("%Y-%m-%d") == date_str]
        df = df[(df["time"].dt.hour >= start) & (df["time"].dt.hour <= end)]
        df = df.set_index("time"); df.columns = [f"{c}_{m}" for c in df.columns]
        dfs.append(df)
    return reduce(lambda l, r: l.join(r, how="outer"), dfs).reset_index()

def plot_forecast(forecast, models, out_path="forecast.png"):
    plt.figure(figsize=(14,10))
    plt.subplot(3,1,1)
    for m in models: plt.plot(forecast["time"], forecast[f"temp_{m}"], marker="o", linestyle="-", label=m)
    plt.ylabel("Temperature (°C)"); plt.title("Temperature Forecast")
    plt.legend(title="Models", bbox_to_anchor=(1.02,1), loc="upper left"); plt.xticks(rotation=45)
    plt.subplot(3,1,2)
    for m in models: plt.plot(forecast["time"], forecast[f"precip_{m}"], marker="s", linestyle="--", label=m)
    plt.ylabel("Precipitation (mm)"); plt.title("Precipitation Forecast")
    plt.legend(title="Models", bbox_to_anchor=(1.02,1), loc="upper left"); plt.xticks(rotation=45)
    plt.subplot(3,1,3)
    for m in models: plt.plot(forecast["time"], forecast[f"wind_{m}"], marker="^", linestyle="-.", label=m)
    plt.ylabel("Wind Speed (km/h)"); plt.title("Wind Speed Forecast")
    plt.legend(title="Models", bbox_to_anchor=(1.02,1), loc="upper left"); plt.xticks(rotation=45)
    plt.tight_layout(); plt.savefig(out_path, dpi=140, bbox_inches="tight"); plt.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌤 Welcome!
Use:\n/forecast <lat> <lon> <timezone> <YYYY-MM-DD> <start_hr> <end_hr> <models>\n"
                                    "Example:\n/forecast 22.26 69.40 Asia/Kolkata 2025-08-19 12 18 GFS,ICON\nSee /models")

async def models_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Supported models: " + ", ".join(AVAILABLE_MODELS.keys()))

async def forecast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) < 7:
            await update.message.reply_text("Usage: /forecast <lat> <lon> <timezone> <YYYY-MM-DD> <start_hr> <end_hr> <models>")
            return
        lat, lon = float(context.args[0]), float(context.args[1])
        tz, date_str = context.args[2], context.args[3]
        start, end = int(context.args[4]), int(context.args[5])
        models = [m.strip() for m in context.args[6].split(",") if m.strip() in AVAILABLE_MODELS]
        if not models:
            await update.message.reply_text("No valid models. Use /models"); return
        fc = build_forecast(lat, lon, tz, date_str, start, end, models)
        txt = fc.to_string(index=False)
        if len(txt) > 3800:
            csv_path = "forecast.csv"; fc.to_csv(csv_path, index=False)
            await update.message.reply_document(open(csv_path,"rb"), caption="Forecast CSV")
            snippet = fc.head(20).to_string(index=False)
            await update.message.reply_text("```
"+snippet+"
```", parse_mode="Markdown")
        else:
            await update.message.reply_text("```
"+txt+"
```", parse_mode="Markdown")
        png = "forecast.png"; plot_forecast(fc, models, png)
        await update.message.reply_photo(open(png,"rb"))
    except Exception as e:
        logger.exception("forecast error"); await update.message.reply_text(f"Error: {e}")

def main():
    if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN env var not set")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("models", models_cmd))
    app.add_handler(CommandHandler("forecast", forecast))
    app.run_polling()

if __name__ == "__main__":
    main()
