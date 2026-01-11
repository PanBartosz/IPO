# ISSUES (wnioski z wymiany e-maili)

Poniżej spis problemów, interpretacji wymagań oraz możliwych rozwiązań (z plusami/minusami). Tam, gdzie w korespondencji pojawiają się propozycje-rozwiązania, próbuję nazwać „prawdziwy problem” (często to klasyczny XY problem: dyskutujemy o rozwiązaniu X, a realny problem Y jest inny).

## 1) Pole „Gender” u nauczycieli (usunięcie „Other”)

**Co jest w systemie teraz**
- `Gender` jest polem wymaganym dla uczniów i nauczycieli; opcje: `Female`, `Male`, `Other`, `Prefer not to say` (`ipo_app/forms.py`).

**Proponowane X w korespondencji**
- „Zostawić tylko dwie płcie u nauczycieli” (usunąć `Other`).

**Prawdopodobny problem Y**
- Zarządzanie ryzykiem wizerunkowym/organizacyjnym + minimalizacja danych wrażliwych; obawa przed sporami i przed „wchodzeniem w sferę intymną”.

**Opcje**
1. **Zachować jak jest (4 opcje)**
   - Plusy: inkluzywność, spójność danych (uczniowie/nauczyciele), mniejsze ryzyko wymuszania nieprawdziwych deklaracji.
   - Minusy: możliwa kontrowersja u części interesariuszy; potrzeba jasnego uzasadnienia po co to pole.
2. **U nauczycieli ograniczyć do `Female/Male/Prefer not to say`**
   - Plusy: „odpolitycznienie” nauczycieli przy zachowaniu „bezpiecznej” opcji odmowy.
   - Minusy: arbitralność; rozjazd między formularzami; możliwe poczucie wykluczenia.
3. **Zrezygnować z pola `Gender` u nauczycieli (a ewentualnie zostawić tylko u uczniów lub wcale)**
   - Plusy: minimalizacja zbieranych danych; redukcja ryzyka RODO i organizacyjnego.
   - Minusy: jeśli pole jest potrzebne operacyjnie (np. zakwaterowanie), trzeba je zastąpić innym, mniej obciążającym pytaniem.

**Rekomendacja (jeśli celem jest „dane operacyjne”, nie „gender”)**
- Zastąpić `Gender` pytaniem o **preferencje/uwarunkowania zakwaterowania** lub „wymagania dot. pokoju” (np. „pokój jednoosobowy / współdzielenie / preferencje/ograniczenia”), bo to bliżej celu i mniej „tożsamościowe”.
- Jeśli `Gender` ma zostać: co najmniej dodać krótką informację „Po co pytamy” i umożliwić odmowę (`Prefer not to say`).

---

## 9) Pilot/zmiana algorytmu oceniania: wpływ skrajnych ocen

**Proponowane X**
- „Wycinanie skrajnych ocen” oraz warianty: 5 recenzentów vs 6 ocen (dodatkowe 2 oceny w wyjątkowych przypadkach) i wtedy uciąć skrajne.

**Prawdopodobny problem Y**
- Odporność wyniku na pojedynczą „skrajną” ocenę przy zachowaniu dyskusji w grupach i sensownego obciążenia recenzentów.

**Krytyczne doprecyzowania**
- Czy oceny powstają **po dyskusji w grupie** (konsensus/kalibracja), czy są niezależne?
- Kiedy uznajemy ocenę za „skrajną”: próg różnicy? odchylenie od mediany? spread > X?
- Czy pilot oznacza: symulację na danych historycznych, czy wdrożenie na żywo dla części esejów?

**Opcje (schematy agregacji)**
1. **4 oceny, bez obcinania** (status quo)
   - Plusy: szybkie.
   - Minusy: wrażliwe na outlier.
2. **5 ocen, obciąć min i max** (zostają 3)
   - Plusy: proste i odporne.
   - Minusy: duże obciążenie; wydłużenie etapów.
3. **4 oceny + reguła „trigger”**: jeśli spread/rozbieżność > próg, dodać 1–2 recenzentów; potem obcinać skrajne i liczyć z pozostałych
   - Plusy: dodatkowy koszt tylko „tam gdzie boli”.
   - Minusy: trudniejsze operacyjnie; trzeba dobrze ustawić progi i komunikację.
4. **Mediana zamiast średniej** (lub średnia ważona po kalibracji)
   - Plusy: odporność na outlier bez dodatkowych recenzji.
   - Minusy: może zmienić intuicję „punktacji” i wymaga akceptacji formalnej.

**Rekomendacja**
- Zacząć od opcji 3 lub 4 jako pilota na danych historycznych: zdefiniować metrykę (np. „ile esejów odpadło przez pojedynczy outlier”) i porównać warianty przed zmianą procesu na żywo.
