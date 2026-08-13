"""
Delad ombalanserings-schemaläggning - upptackt 2026-07-29 vid granskning
av HYP-012/HYP-014 (samma bugg i bada, delad kod-struktur).

BUGGEN: bade HYP-012 och HYP-014 byggde ombalanseringsdatum via
`close.resample("ME"/"QE").last().index`. Detta ger KALENDER-periodslut
som indexetiketter (t.ex. 2023-12-31, 2024-03-31, 2024-06-30) - INTE
nodvandigtvis en riktig handelsdag. Huvudloopen kollade sedan
`if date in rebal_set` dar `date` itererar over den FAKTISKA
handelskalendern (close.index). Nar en kalenderetikett rakar vara en
lordag/sondag/helgdag (vilket den ar ~30% av gangerna - se sanity-check
nedan) sa matchar den ALDRIG nagon rad i loopen, och HELA den
ombalanseringen hoppas tyst over - ingen varning, inget fel.

Konkret konsekvens (HYP-014, ticker ESSA): tre kvartal i rad
(2023-12-31, 2024-03-31, 2024-06-30 - alla lorda/sondagar) hoppades
over. En ticker vars pris blev korrupt exakt i det fonstret red darfor
okontrollerat i 9 manader tills nasta RIKTIGA handelsdag i rebal-schemat
(2024-09-30, en mandag), och bokade da en enda +5424%-trade som
dominerade hela det rapporterade resultatet.

FIXEN: snap varje kalenderetikett till narmaste FAKTISKA handelsdag
<= etiketten (aldrig efter - det vore look-ahead) via
`trading_index.asof(label)`. Universumets manads-nyckel-uppslagning
(`universe_by_month.get(month_key)`) maste fortfarande anvanda den
URSPRUNGLIGA kalenderetiketten (universumfilen ar byggd med kalender-
manadsslut som nycklar) - bara SJALVA EXEKVERINGSDATUMET i backtest-
loopen ska vara den snappade handelsdagen. Denna modul returnerar bada,
parade, sa anropande kod inte kan blanda ihop dem.
"""

import pandas as pd


def snap_rebalance_dates(calendar_dates: pd.DatetimeIndex, trading_index: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Mappar kalender-periodslutsetiketter (fran t.ex. close.resample(...).last().index,
    som kan falla pa icke-handelsdagar) till narmaste FAKTISKA handelsdag <= etiketten.

    Returnerar en DataFrame med kolumnerna:
      - calendar_label:  den ursprungliga kalenderetiketten (anvand denna,
                          strftime("%Y-%m-%d"), for universe_by_month-uppslagning)
      - execution_date:  den faktiska handelsdag da ombalanseringen kors
                          (anvand denna for `if date == execution_date` i backtest-loopen)

    En rad per INPUT-kalenderdatum som har ett giltigt snap-mal (kalenderdatum
    fore handelskalenderns forsta dag ger inget mal och utesluts tyst - de
    ligger per konstruktion utanfor backtest-perioden anda).

    Deduplicerar pa execution_date (behaller den SENASTE calendar_label om
    flera kalenderetiketter skulle snappa till samma handelsdag, t.ex. vid
    ett ovanligt langt handelsuppehall) - annars skulle samma handelsdag
    trigga tva ombalanseringar i foljd i anropande kod.
    """
    rows = []
    for label in calendar_dates:
        snapped = trading_index.asof(label)
        if pd.isna(snapped):
            continue
        rows.append({"calendar_label": label, "execution_date": snapped})

    if not rows:
        return pd.DataFrame(columns=["calendar_label", "execution_date"])

    df = pd.DataFrame(rows).sort_values("calendar_label")
    df = df.drop_duplicates(subset="execution_date", keep="last").reset_index(drop=True)
    return df


if __name__ == "__main__":
    # Sanity-check: kvantifierar hur ofta kalenderetiketter INTE ar
    # handelsdagar (samma matt som upptackte buggens omfattning
    # 2026-07-29), och verifierar att snappningen tar bort alla luckor.
    trading_index = pd.bdate_range("2010-01-01", "2024-12-31")  # forenklad, ingen helgdagskalender behovs för detta testet

    for freq, label in [("ME", "manatlig"), ("QE", "kvartalsvis")]:
        s = pd.Series(range(len(trading_index)), index=trading_index)
        calendar_dates = s.resample(freq).last().index
        missing = [d for d in calendar_dates if d not in trading_index]
        print(f"{label}: {len(calendar_dates)} kalenderetiketter, "
              f"{len(missing)} ({len(missing) / len(calendar_dates):.0%}) faller pa icke-handelsdagar")

        snapped = snap_rebalance_dates(calendar_dates, trading_index)
        assert snapped["execution_date"].isin(trading_index).all(), "snappat datum maste alltid vara en riktig handelsdag"
        assert len(snapped) <= len(calendar_dates)
        print(f"  -> efter snap_rebalance_dates: {len(snapped)} unika exekveringsdatum, "
              f"samtliga bekraftat riktiga handelsdagar.\n")

    print("OK: alla snappade exekveringsdatum ar riktiga handelsdagar (inga tysta hopp kvar).")
