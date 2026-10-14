"""
Algorithme urne de jetons — AMSEN Parrainage
Port Python de src/lib/urne.ts (Next.js)

Règles :
  - q, r = divmod(nb_nouveaux, nb_parrains)
  - Chaque parrain reçoit q jetons ; r parrains choisis au hasard en reçoivent 1 de plus.
  - tier = tour de tirage (0 = 1er filleul, 1 = 2e, …)
  - Le tirage épuise tous les jetons du tier courant avant de passer au suivant.
  - Tout hasard vient de `secrets` (cryptographique), jamais de `random`.
"""
import secrets
import hashlib
from django.db import transaction
from .models import Filiere, Etudiant, Jeton, Evenement, Parrainage, JournalAudit


FILIERE_COULEUR = {
    "AS": "#1F7A3A",
    "ISE_ECO": "#FFD800",
    "ISE_MATH": "#C62F24",
    "ISEP": "#1F7A3A",
}

FILIERE_LIBELLE = {
    "AS": "Analyste statisticien",
    "ISE_ECO": "Ingénieur statisticien économiste",
    "ISE_MATH": "Ingénieur statisticien économiste",
    "ISEP": "Cycle Ingénieurs",
}


def crypto_shuffle(lst: list) -> list:
    """Fisher-Yates cryptographique avec secrets.randbelow."""
    a = list(lst)
    for i in range(len(a) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        a[i], a[j] = a[j], a[i]
    return a


def crypto_randint(n: int) -> int:
    """Entier aléatoire dans [0, n) via secrets."""
    return secrets.randbelow(n)


# ---------------------------------------------------------------------------
# 1) Événement actif
# ---------------------------------------------------------------------------

def get_evenement_actif():
    """Retourne l'événement non-terminé le plus récent, ou le dernier sinon."""
    ev = Evenement.objects.filter(statut__in=["preparation", "en_cours"]).order_by("-created_at").first()
    if ev:
        return ev
    return Evenement.objects.order_by("-created_at").first()


# ---------------------------------------------------------------------------
# 2) Préparer urne pour (filière, niveau)
# ---------------------------------------------------------------------------

def preparer_urne(parrains: list, nb_nouveaux: int, evenement, filiere_code: str, niveau: int) -> list:
    """
    Construit les jetons pour (filière, niveau) et les sauvegarde en base.
    Retourne la liste des ids de jetons créés.
    """
    n = len(parrains)
    if n == 0 or nb_nouveaux == 0:
        return []

    q, r = divmod(nb_nouveaux, n)
    # r parrains choisis aléatoirement reçoivent un jeton supplémentaire
    lucky_indices = set(crypto_shuffle(list(range(n)))[:r])

    # Construire la liste de jetons par tier
    jetons_par_parrain = {}
    for i, parrain in enumerate(parrains):
        nb_jetons = q + (1 if i in lucky_indices else 0)
        jetons_par_parrain[parrain.id] = nb_jetons

    all_jetons = []
    max_tier = max(jetons_par_parrain.values()) if jetons_par_parrain else 0
    for tier in range(max_tier):
        tier_jetons = [
            pid for pid, nb in jetons_par_parrain.items() if tier < nb
        ]
        tier_jetons_shuffled = crypto_shuffle(tier_jetons)
        for pid in tier_jetons_shuffled:
            all_jetons.append({"parrain_id": pid, "tier": tier})

    # Mélange global du tier pour l'ordre
    all_jetons_shuffled = crypto_shuffle(all_jetons)

    created_ids = []
    jetons_bulk = []
    for i, j in enumerate(all_jetons_shuffled):
        jeton = Jeton(
            evenement=evenement,
            filiere_id=filiere_code,
            niveau=niveau,
            parrain_id=j["parrain_id"],
            tier=j["tier"],
            ordre=i,
            utilise=False,
        )
        jetons_bulk.append(jeton)

    created = Jeton.objects.bulk_create(jetons_bulk)
    return [j.id for j in created]


# ---------------------------------------------------------------------------
# 3) Tirer un jeton
# ---------------------------------------------------------------------------

def tirer_jeton(filiere_code: str, niveau: int, evenement):
    """
    Tire cryptographiquement un jeton disponible du tier courant.
    Retourne l'objet Jeton (avec parrain chargé) ou None si urne vide.
    """
    with transaction.atomic():
        # Trouver le tier minimum disponible
        min_tier_row = (
            Jeton.objects
            .filter(evenement=evenement, filiere_id=filiere_code, niveau=niveau, utilise=False)
            .order_by("tier")
            .values("tier")
            .first()
        )
        if not min_tier_row:
            return None
        min_tier = min_tier_row["tier"]

        # Jetons disponibles de ce tier
        dispos = list(
            Jeton.objects
            .select_for_update()
            .filter(evenement=evenement, filiere_id=filiere_code, niveau=niveau, utilise=False, tier=min_tier)
        )
        if not dispos:
            return None

        # Tirage cryptographique
        idx = crypto_randint(len(dispos))
        jeton = dispos[idx]
        jeton.utilise = True
        jeton.save(update_fields=["utilise"])

    return Jeton.objects.select_related("parrain", "parrain__filiere").get(pk=jeton.id)


# ---------------------------------------------------------------------------
# 4) Générer toutes les urnes
# ---------------------------------------------------------------------------

def generer_toutes_urnes(evenement) -> str:
    """
    Génère les urnes pour toutes les filières et niveaux parrain.
    Supprime d'abord les anciens jetons.
    Retourne l'empreinte SHA-256.
    """
    # Supprimer les anciens jetons de cet événement
    Jeton.objects.filter(evenement=evenement).delete()

    filieres = Filiere.objects.all().order_by("ordre")
    all_ids = []

    for filiere in filieres:
        nb_nouveaux = Etudiant.objects.filter(
            filiere=filiere, niveau=1, tire=False, absent=False
        ).count()
        if nb_nouveaux == 0:
            continue

        for niveau in [2, 3]:
            parrains = list(
                Etudiant.objects.filter(filiere=filiere, niveau=niveau, absent=False)
            )
            if not parrains:
                continue

            ids = preparer_urne(parrains, nb_nouveaux, evenement, filiere.code, niveau)
            all_ids.extend(ids)

    sorted_ids = sorted(str(i) for i in all_ids)
    empreinte = hashlib.sha256("|".join(sorted_ids).encode()).hexdigest()
    return empreinte


# ---------------------------------------------------------------------------
# 5) Calculer les stats globales (optimisé : requêtes groupées parallèles)
# ---------------------------------------------------------------------------

def calculer_stats():
    """
    Retourne un dict de StatsGlobales.
    Utilise des annotations groupées pour minimiser les requêtes SQL.
    """
    from django.db.models import Count, Q

    event = get_evenement_actif()

    filieres = list(Filiere.objects.all().order_by("ordre"))

    # Grouper les comptes étudiants par (filiere, niveau) en une seule requête
    etu_counts = (
        Etudiant.objects
        .values("filiere_id", "niveau")
        .annotate(total=Count("id"))
    )
    etu_map = {(r["filiere_id"], r["niveau"]): r["total"] for r in etu_counts}

    # Comptes des nouveaux parrainés (tire=True) par filière
    parraines_counts = (
        Etudiant.objects
        .filter(niveau=1, tire=True)
        .values("filiere_id")
        .annotate(total=Count("id"))
    )
    parraines_map = {r["filiere_id"]: r["total"] for r in parraines_counts}

    # Jetons restants par (filière, niveau)
    jetons_map = {}
    if event:
        jetons_counts = (
            Jeton.objects
            .filter(evenement=event, utilise=False)
            .values("filiere_id", "niveau")
            .annotate(total=Count("id"))
        )
        jetons_map = {(r["filiere_id"], r["niveau"]): r["total"] for r in jetons_counts}

    stats_filieres = []
    total_nouveaux = 0
    total_parraines = 0
    total_restants = 0

    for f in filieres:
        total_n = etu_map.get((f.code, 1), 0)
        parraines = parraines_map.get(f.code, 0)
        parrains_2a = etu_map.get((f.code, 2), 0)
        parrains_3a = etu_map.get((f.code, 3), 0)
        jetons_2a = jetons_map.get((f.code, 2), 0)
        jetons_3a = jetons_map.get((f.code, 3), 0)

        restants = total_n - parraines
        total_nouveaux += total_n
        total_parraines += parraines
        total_restants += restants

        stats_filieres.append({
            "code": f.code,
            "libelle": f.libelle,
            "couleur": f.couleur,
            "totalNouveaux": total_n,
            "parraines": parraines,
            "restants": restants,
            "parrains2A": parrains_2a,
            "parrains3A": parrains_3a,
            "jetons2ARestants": jetons_2a,
            "jetons3ARestants": jetons_3a,
        })

    return {
        "totalNouveaux": total_nouveaux,
        "totalParraines": total_parraines,
        "totalRestants": total_restants,
        "filieres": stats_filieres,
        "urnesGenerees": event.urnes_generees if event else False,
        "evenementId": event.id if event else None,
        "statut": event.statut if event else "preparation",
        "filiereActive": event.filiere_active if event else "AS",
        "evenementNom": event.nom if event else None,
        "modeAnimation": event.mode_animation if event else "cartes",
        "difficulte": event.difficulte if event else "moyen",
    }

