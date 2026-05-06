# Поисковые запросы для hh.ru

Ротировать запросы при каждом запуске. Фильтры: Санкт-Петербург, офис или гибрид, зарплата от 180к.

## Основные (использовать всегда)
1. `инженер конструктор`
2. `реверс инжиниринг`

## Дополнительные (ротация, 2-3 за запуск)
3. `инженер КОМПАС-3D`
4. `инженер SolidWorks`
5. `3D сканирование инженер`
6. `конструктор нефтегазовое оборудование`
7. `инженер проектировщик машиностроение`
8. `Geomagic инженер`
9. `конструктор импортозамещение`

## Формат URL
Санкт-Петербург, зарплата от 180 000, офис+гибрид (без фильтра remote):
```
https://hh.ru/search/vacancy?text={запрос}&area=2&salary=180000&only_with_salary=true&work_format=OFFICE&work_format=HYBRID&enable_snippets=true&ored_clusters=true&order_by=relevance
```

Без фильтра зарплаты (если мало результатов):
```
https://hh.ru/search/vacancy?text={запрос}&area=2&work_format=OFFICE&work_format=HYBRID&enable_snippets=true&ored_clusters=true&order_by=relevance
```
