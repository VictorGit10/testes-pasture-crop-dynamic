"""Testes sintéticos do motor de episódios (regras da Decisão 024 e da decomposição de entrada do Mario).

Rodar: python -I test_motor.py   (sai com erro se algum caso falhar)
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testes_goias_c11 as T  # noqa: E402

P, X, N, D, M, Z = T.PAS, T.TMP, T.NAT, T.NOD, T.MOS, T.NONE

# sequência -> (orig esperado, kind esperado, prev esperado na última posição)
CASOS = {
    "PAS PAS TMP PAS PAS": ([P, P, X, P, P], [1, 1, 0, 2, 2], [0, 0, 0, 2, 2], X),
    "PAS NAT PAS NAT PAS": ([P, N, P, N, P], [1, 0, 2, 0, 2], [0, 0, 2, 0, 2], N),
    "NAT PAS PAS": ([N, P, P], [0, 2, 2], [0, 1, 1], N),
    "PAS NOD PAS": ([P, D, P], [1, 0, 3], [0, 0, 0], T.NONE),
    "NAT NOD NAT PAS": ([N, D, N, P], [0, 0, 0, 2], [0, 0, 0, 3], N),
    "PAS NOD TMP PAS": ([P, D, X, P], [1, 0, 0, 2], [0, 0, 0, 2], X),
    "NAT MOS PAS TMP PAS": ([N, M, P, X, P], [0, 0, 2, 0, 2], [0, 0, 1, 0, 2], X),
    # casos acrescentados após a revisão de 14/11 (código 0 = máscara)
    "NONE NAT PAS": ([Z, N, P], [0, 0, 2], [0, 0, 3], N),
    "PAS NONE PAS": ([P, Z, P], [1, 0, 3], [0, 0, 0], T.NONE),
    "NOD(1985) NAT PAS": ([D, N, P], [0, 0, 2], [0, 0, 3], N),
}


def main():
    falhas = 0
    for nome, (s, o_esp, k_esp, prev_esp) in CASOS.items():
        L = len(s)
        G = np.array(s + [s[-1]] * (T.NY - L), np.uint8)[:, None]
        o, k, p, _ = T.motor(G, None)
        ok = o[:L, 0].tolist() == o_esp and k[:L, 0].tolist() == k_esp and int(p[L - 1, 0]) == prev_esp
        falhas += not ok
        print(("ok   " if ok else "FALHA"), nome, o[:L, 0].tolist(), k[:L, 0].tolist(), T.NOMES[p[L - 1, 0]])
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
