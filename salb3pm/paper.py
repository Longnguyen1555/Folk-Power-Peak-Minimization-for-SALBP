"""Original MSAT-E binary formulation and reduction rules, without CLI state.

PB encoding is explicitly Binary Merger. Bounds and bit counts are normalized.
This factory is kept separate from the shared pairwise/staircase formulation.
"""

from math import ceil, floor
from pysat.formula import CNF, WCNF, IDPool
from pysat.pb import PBEnc, EncType
import pysat.card as card


def build_paper_wcnf(instance):
    card_encoding = card.EncType.cardnetwrk
    PB_encoding = EncType.binmerge
    neg_X = {}
    neg_XS_pair = {}
    pos_A = {}
    vpool = IDPool(start_from=1)
    X = lambda j, k: vpool.id("X{0}@{1}".format(j, k))
    S = lambda j, t: vpool.id("S{0}@{1}".format(j, t))
    A = lambda j, t: vpool.id("A{0}@{1}".format(j, t))
    E = lambda j: vpool.id("E{0}".format(j))

    def get_single_machine_time(ealiest_st_time, T):
        C_max = 0
        st_T_pair = sorted(list(zip(ealiest_st_time, T)))
        for r, t in st_T_pair:
            C_max = max(C_max, r) + t
        return C_max

    def get_precedence_constraints(n, m, c, T, W, precedence_relations):
        pre_list = [[] for _ in range(n + 1)]
        pre_task_list = [{i} for i in range(n + 1)]
        pre_time_list = [0] * (n + 1)
        suc_list = [[] for _ in range(n + 1)]
        suc_task_list = [{i} for i in range(n + 1)]
        suc_time_list = [0] * (n + 1)
        in_degree = [0] * (n + 1)
        que = [0] * (n + 1)
        ql = 0
        qr = 0
        topo_list = []
        tau_list = [0] * (n + 1)
        tau_r_list = [0] * (n + 1)
        for i, j in precedence_relations:
            pre_list[j].append(i)
            suc_list[i].append(j)
            in_degree[j] += 1
        for i in range(1, n + 1):
            if in_degree[i] == 0:
                que[qr] = i
                qr += 1
        while ql != qr:
            me = que[ql]
            ql += 1
            topo_list.append(me)
            for tt in suc_list[me]:
                in_degree[tt] -= 1
                if in_degree[tt] == 0:
                    que[qr] = tt
                    qr += 1
        for me in topo_list:
            for suc in suc_list[me]:
                pre_task_list[suc] = pre_task_list[suc].union(pre_task_list[me])
            pre_time_list[me] = sum([T[pre] for pre in pre_task_list[me]])
            tau_i = (ceil(pre_time_list[me] / c) - 1) * c
            single_machine_value = get_single_machine_time(
                [tau_list[j] for j in pre_task_list[me] if j != me],
                [T[j] for j in pre_task_list[me] if j != me],
            )
            tau_i = max(tau_i, single_machine_value)
            if tau_i > floor(tau_i / c) * c and len(pre_list[me]) != 0:
                tau_i = max(
                    tau_i, floor(tau_i / c) * c + min([T[j] for j in pre_list[me]])
                )
            if ceil((tau_i + T[me]) / c) > floor(tau_i / c) + 1:
                tau_i = (floor(tau_i / c) + 1) * c
            tau_list[me] = tau_i
        for me in topo_list[::-1]:
            for pre in pre_list[me]:
                suc_task_list[pre] = suc_task_list[pre].union(suc_task_list[me])
            suc_time_list[me] = sum([T[suc] for suc in suc_task_list[me]])
            tau_i_r = (ceil(suc_time_list[me] / c) - 1) * c
            single_machine_value = get_single_machine_time(
                [tau_r_list[j] for j in suc_task_list[me] if j != me],
                [T[j] for j in suc_task_list[me] if j != me],
            )
            tau_i_r = max(tau_i_r, single_machine_value)
            if tau_i_r > floor(tau_i_r / c) * c and len(suc_list[me]) != 0:
                tau_i_r = max(
                    tau_i_r, floor(tau_i_r / c) * c + min([T[j] for j in suc_list[me]])
                )
            if ceil((tau_i_r + T[me]) / c) > floor(tau_i_r / c) + 1:
                tau_i_r = (floor(tau_i_r / c) + 1) * c
            tau_r_list[me] = tau_i_r
        cnf_precedence = CNF()
        for i in range(1, n + 1):
            impossible_station_l = tau_list[i] // c
            for j in range(1, impossible_station_l + 1):
                cnf_precedence.append([-X(i, j)])
                neg_X[X(i, j)] = 1
            assert impossible_station_l < m
            l_slot = tau_list[i] - c * impossible_station_l
            for t in range(l_slot):
                cnf_precedence.append([-X(i, impossible_station_l + 1), -S(i, t)])
                neg_XS_pair[X(i, impossible_station_l + 1), S(i, t)] = 1
            tau_r_list[i] += T[i] - 1
            impossible_station_r = tau_r_list[i] // c
            for j in range(1, impossible_station_r + 1):
                cnf_precedence.append([-X(i, m - j + 1)])
                neg_X[X(i, m - j + 1)] = 1
            assert impossible_station_r < m
            r_slot = tau_r_list[i] - c * impossible_station_r
            for t in range(1, r_slot + 1):
                cnf_precedence.append([-X(i, m - impossible_station_r), -S(i, c - t)])
                neg_XS_pair[X(i, m - impossible_station_r), S(i, c - t)] = 1
        return cnf_precedence

    def get_longTask_constraints(n, m, c, T, W, precedence_relations):
        LongTask_cnf = CNF()
        for i in range(1, n + 1):
            l = c - T[i]
            r = T[i] - 1
            if l > r:
                continue
            for t in range(l, r + 1):
                pos_A[A(i, t)] = 1
                LongTask_cnf.append([A(i, t)])
        return LongTask_cnf

    def get_wcnf_insatance(n, m, c, T, W, precedence_relations, vpool, ub, lb):
        wcnf = WCNF()
        nb_E = ub.bit_length()
        for i in range(nb_E):
            wcnf.append([-E(i)], weight=2**i)
        for k in range(1, m + 1):
            lits = []
            weight = []
            for j in range(1, n + 1):
                if X(j, k) in neg_X:
                    continue
                lits.append(X(j, k))
                weight.append(T[j])
            wcnf.extend(
                PBEnc.leq(
                    lits=lits,
                    weights=weight,
                    bound=c,
                    vpool=vpool,
                    encoding=PB_encoding,
                )
            )
        for j in range(1, n + 1):
            wcnf.extend(
                card.CardEnc.equals(
                    lits=[X(j, k) for k in range(1, m + 1) if X(j, k) not in neg_X],
                    bound=1,
                    encoding=card_encoding,
                    vpool=vpool,
                )
            )
            wcnf.extend(
                card.CardEnc.equals(
                    lits=[S(j, t) for t in range(0, c - T[j] + 1)],
                    bound=1,
                    encoding=card_encoding,
                    vpool=vpool,
                )
            )
            for k in range(1, m + 1):
                for i in range(1, j):
                    wcnf.extend(
                        [
                            [-X(i, k), -X(j, k), -A(i, t), -A(j, t)]
                            for t in range(0, c)
                            if X(i, k) not in neg_X
                            if X(j, k) not in neg_X
                        ]
                    )
            for t in range(0, c - T[j] + 1):
                for t_prime in range(c):
                    if t_prime >= t and t_prime - t < T[j]:
                        if A(j, t_prime) not in pos_A:
                            wcnf.append([-S(j, t), A(j, t_prime)])
                    else:
                        wcnf.append([-S(j, t), -A(j, t_prime)])
            wcnf.extend([[-S(j, t)] for t in range(c - T[j] + 1, c)])
        for i, j in precedence_relations:
            for k in range(1, m + 1):
                bound = k
                lits = [X(j, k)] if X(j, k) not in neg_X else []
                for h in range(1, k + 1):
                    if X(i, h) in neg_X:
                        bound -= 1
                        continue
                    lits.append(-X(i, h))
                wcnf.extend(
                    card.CardEnc.atmost(
                        lits=lits, bound=bound, encoding=card_encoding, vpool=vpool
                    )
                )
                for t in range(0, c - T[j] + 1):
                    S_lits = [-S(i, tau) for tau in range(0, t - T[i] + 1)]
                    wcnf.extend(
                        card.CardEnc.atmost(
                            lits=[S(j, t), X(i, k), X(j, k)] + S_lits,
                            bound=2 + len(S_lits),
                            encoding=card_encoding,
                            vpool=vpool,
                        )
                    )
        lits = [E(x) for x in range(nb_E)]
        weights = [2**x for x in range(nb_E)]
        wcnf.extend(
            PBEnc.geq(
                lits=lits, weights=weights, bound=lb, vpool=vpool, encoding=PB_encoding
            )
        )
        l_ub = sum([2**i for i in range(nb_E)])
        for t in range(c):
            lits = [A(j, t) for j in range(1, 1 + n)] + [-E(x) for x in range(nb_E)]
            weights = [W[j] for j in range(1, 1 + n)] + [2**x for x in range(nb_E)]
            wcnf.extend(
                PBEnc.leq(
                    lits=lits,
                    weights=weights,
                    bound=l_ub,
                    vpool=vpool,
                    encoding=PB_encoding,
                )
            )
        return wcnf

    def merge_wcnf(wcnf1, wcnf2):
        for clause in wcnf2.hard:
            wcnf1.append(clause)
        for clause, weight in zip(wcnf2.soft, wcnf2.wght):
            wcnf1.append(clause, weight=weight)
        wcnf1.topw = max(wcnf1.topw, wcnf2.topw)
        return wcnf1

    n, m, c = instance.n, instance.stations, instance.cycle
    T, W = [0, *instance.durations], [0, *instance.powers]
    precedence = [(i + 1, j + 1) for i, j in instance.precedence]
    try:
        reductions = get_precedence_constraints(n, m, c, T, W, precedence)
    except AssertionError:
        infeasible = WCNF()
        infeasible.append([])
        return infeasible
    wcnf = WCNF()
    wcnf.extend(reductions)
    wcnf.extend(get_longTask_constraints(n, m, c, T, W, precedence))
    return merge_wcnf(
        wcnf,
        get_wcnf_insatance(
            n,
            m,
            c,
            T,
            W,
            precedence,
            vpool,
            instance.peak_upper_bound,
            instance.peak_lower_bound,
        ),
    )
