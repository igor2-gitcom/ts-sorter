# ts-sorter

Сортировка видеоархива MPEG-2 TS с помощью YOLO: файлы раскладываются по категориям, ведётся отчёт о появлении людей и техники.

## Возможности
- Мониторинг папки `data/incoming` (`*.ts`, `*.m2ts`, `*.mts`)
- Проверка читаемости файлов через `ffprobe`, анализ кадров через OpenCV + YOLOv8
- Раскладка по папкам:

| Папка | Условие |
|---|---|
| `data/1_people` | в кадре обнаружены люди |
| `data/2_vehicles` | людей нет, есть автомобили/техника |
| `data/3_unreadable` | файл не открывается / не декодируется |
| `data/4_other` | всё остальное |

- Веб-интерфейс `/` — вкладки: исходный архив + 4 категории, просмотр в браузере (TS → fMP4 на лету)
- Отчёт `/report` — время появления/исчезновения людей и техники, ссылка на файл, экспорт CSV

## Быстрый старт
```bash
git clone https://github.com/<user>/ts-sorter.git && cd ts-sorter
cp .env.example .env
cp /path/to/archive/*.ts data/incoming/
docker compose up -d --build
```
Откройте http://localhost:8000 и http://localhost:8000/report

## Настройки (`.env`)
| Переменная | По умолчанию | Описание |
|---|---|---|
| `SAMPLE_SEC` | `1.0` | шаг анализа кадров, сек |
| `CONF` | `0.45` | порог уверенности YOLO |
| `SCAN_INTERVAL` | `30` | период опроса папки, сек |
| `SORT_MODE` | `link` | `link` — hardlink/копия, `move` — перенос |

## API
| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/files?category=all\|people\|vehicles\|unreadable\|other` | список файлов |
| GET | `/api/events?kind=all\|person\|vehicle` | события детекции |
| POST | `/api/rescan/{id}` | повторный анализ файла |
| GET | `/media/{id}` | скачать исходный `.ts` |
| GET | `/play/{id}?t=сек` | воспроизведение в браузере с позиции |

## Локальный запуск без Docker
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt     # нужен ffmpeg в системе
DATA_DIR=./data uvicorn app.main:app --port 8000
```

## Своя модель
Замените `yolov8n.pt` в `app/analyzer.py` на свою модель (например, обученную на спецтехнике) и добавьте её классы в словарь `VEHICLE`.

## Структура
```
app/
  main.py        FastAPI: UI, API, стриминг
  analyzer.py    ffprobe + YOLO, сортировка
  db.py          SQLite (data/index.db)
  static/        index.html, report.html, style.css
Dockerfile
docker-compose.yml
.github/workflows/ci.yml
```

## Лицензия
MIT
