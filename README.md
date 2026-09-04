# ITU CRN Monitor

ITU OBS ders programinda belirli lisans CRN'lerini takip eden ve kontenjan acildiginda bildirim gonderebilen Python botu.

## Ozellikler

- Sadece lisans derslerini takip eder.
- Ders brans kodu ve CRN ciftleriyle calisir.
- OBS ders programi endpoint'lerinden dogrudan veri okur.
- Surekli izleme veya tek seferlik kontrol yapabilir.
- Telegram bildirimi icin hazirdir.

## Kurulum

```powershell
pip install -r requirements.txt
```

Ilk ayarlari yapmak icin:

```powershell
python main.py --setup
```

`config.json` icinde ders yoksa `python main.py` komutu da otomatik olarak kurulum sihirbazini acar.

## PowerShell Kullanimi

Kurulum sihirbazini baslat:

```powershell
python main.py --setup
```

Bir brans kodu gir, sonra o bransa ait bir veya daha fazla CRN gir. Birden fazla CRN icin virgul kullan:

```text
Ders brans kodu: BLG
BLG icin takip edilecek CRN(ler): 14251,14250,14711
Ders brans kodu: MAT
MAT icin takip edilecek CRN(ler): 12654,12635
Ders brans kodu:
```

Brans kodu sorusunda bos Enter'a basinca kayit tamamlanir.

Botu surekli calistir:

```powershell
python main.py
```

Sonsuz donguye girmeden tek kontrol yap:

```powershell
python main.py --check-once
```

## Config Ornegi

```json
{
    "program_level": "LS",
    "tracked_courses": [
        {
            "branch_code": "BLG",
            "crns": [
                12462
            ]
        }
    ],
    "polling_interval_minutes": 5,
    "notifications_enabled": false,
    "telegram_bot_token": "",
    "telegram_chat_id": ""
}
```

Gercek token ve chat id bilgilerini `config.json` icinde tutun. `config.json` git tarafindan ignore edilir.
