"""AspersãoPro — núcleo de engenharia para projeto de irrigação por aspersão.

O pacote é independente da interface (Streamlit) e pode ser usado em scripts,
notebooks e análises em lote. Todas as rotinas seguem referências consagradas:

* FAO-56 (Allen et al., 1998) — evapotranspiração e coeficientes de cultura;
* Christiansen (1942) — coeficiente de uniformidade e fator F de múltiplas saídas;
* Keller & Bliesner (1990/2001) — critérios de projeto de aspersão;
* Hazen-Williams / Darcy-Weisbach (Swamee-Jain) — perdas de carga;
* Trimmer (1987) — perdas por evaporação e deriva;
* Bernardo, Mantovani & Soares (Manual de Irrigação) — prática brasileira.
"""

__version__ = "1.0.0"
NOME_PROGRAMA = "AspersãoPro"
