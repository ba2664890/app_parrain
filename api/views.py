"""
Vues API Django REST Framework — AMSEN Parrainage
Port complet des routes Next.js /api/*
"""
import secrets
import json
import csv
import io
import unicodedata
from django.http import HttpResponse
from django.utils import timezone
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Etudiant, Evenement, Parrainage, JournalAudit, Filiere, Jeton
from .serializers import EtudiantSerializer, ParrainageSerializer, AuditSerializer
from .urne import (
    get_evenement_actif,
    calculer_stats,
    generer_toutes_urnes,
    tirer_jeton,
    FILIERE_COULEUR,
    FILIERE_LIBELLE,
    crypto_randint,
)
from .broadcast import broadcast


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def map_etudiant(e: Etudiant) -> dict:
    return {
        "id": e.id,
        "nom": e.nom,
        "prenom": e.prenom,
        "filiereCode": e.filiere_id,
        "niveau": e.niveau,
        "photo": e.photo,
        "telephone": e.telephone,
        "email": e.email,
        "indice1": e.indice1,
        "indice2": e.indice2,
        "indice3": e.indice3,
        "absent": e.absent,
        "tire": e.tire,
    }


# ---------------------------------------------------------------------------
# GET /api/stats/
# ---------------------------------------------------------------------------

class StatsView(APIView):
    def get(self, request):
        try:
            stats = calculer_stats()
            return Response(stats, headers={"Cache-Control": "no-store"})
        except Exception as e:
            return Response({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# POST /api/evenements/
# ---------------------------------------------------------------------------

class EvenementView(APIView):
    def post(self, request):
        nom = request.data.get("nom", "").strip()
        if not nom:
            return Response({"error": "Le nom de la cérémonie est requis"}, status=400)

        active = get_evenement_actif()
        if active and active.statut != "termine":
            return Response(
                {"error": f"Une cérémonie est déjà en cours : {active.nom}"},
                status=409,
            )

        event = Evenement.objects.create(
            nom=nom,
            statut="preparation",
            mode_animation="cartes",
            difficulte="moyen",
            filiere_active="AS",
            urnes_generees=False,
        )
        JournalAudit.enregistrer(event, "evenement_cree", "pilote", {"nom": nom})
        stats = calculer_stats()
        broadcast("stats:update", stats)
        return Response({"ok": True, "evenement": {"id": event.id, "nom": event.nom}})


# ---------------------------------------------------------------------------
# POST /api/tirage/prochain/
# ---------------------------------------------------------------------------

class TirageProchainView(APIView):
    def post(self, request):
        filiere_param = request.data.get("filiere", "").strip()
        if not filiere_param:
            return Response({"error": "Choisissez une filière avant de lancer le tirage"}, status=400)

        event = get_evenement_actif()
        if not event:
            return Response({"error": "Aucun événement actif"}, status=400)
        if not event.urnes_generees:
            return Response({"error": "Les urnes doivent être générées avant le tirage"}, status=409)

        if not Filiere.objects.filter(code=filiere_param).exists():
            return Response({"error": "Filière inconnue"}, status=400)

        candidats = list(
            Etudiant.objects.filter(
                niveau=1, filiere_id=filiere_param, tire=False, absent=False
            )
        )
        if not candidats:
            stats = calculer_stats()
            broadcast("stats:update", stats)
            return Response({"nouveau": None})

        idx = crypto_randint(len(candidats))
        nouveau = map_etudiant(candidats[idx])
        return Response({"nouveau": nouveau})


# ---------------------------------------------------------------------------
# POST /api/tirage/executer/
# ---------------------------------------------------------------------------

class TirageExecuterView(APIView):
    def post(self, request):
        nouveau_id = request.data.get("nouveauId", "").strip()
        if not nouveau_id:
            return Response({"error": "nouveauId requis"}, status=400)

        try:
            filleul = Etudiant.objects.select_related("filiere").get(pk=nouveau_id, niveau=1)
        except Etudiant.DoesNotExist:
            return Response({"error": f"Nouveau introuvable : {nouveau_id}"}, status=404)

        if filleul.tire:
            return Response({"error": f"Nouveau {filleul.prenom} {filleul.nom} déjà tiré"}, status=409)
        if filleul.absent:
            return Response({"error": f"Nouveau {filleul.prenom} {filleul.nom} est absent"}, status=409)

        event = get_evenement_actif()
        if not event:
            return Response({"error": "Aucun événement actif"}, status=400)
        if not event.urnes_generees:
            return Response({"error": "Les urnes doivent être générées avant le tirage"}, status=409)

        try:
            with transaction.atomic():
                # Tire un parrain 2A et un parrain 3A
                jeton2 = tirer_jeton(filleul.filiere_id, 2, event)
                if not jeton2:
                    return Response({"error": "urne vide"}, status=409)

                jeton3 = tirer_jeton(filleul.filiere_id, 3, event)
                if not jeton3:
                    return Response({"error": "Aucun parrain 3A disponible"}, status=409)

                # Marquer le nouveau comme tiré
                filleul.tire = True
                filleul.save(update_fields=["tire"])

                parrain2 = jeton2.parrain
                parrain3 = jeton3.parrain

                # Créer les parrainages
                Parrainage.objects.create(
                    evenement=event,
                    filleul=filleul,
                    parrain=parrain2,
                    niveau=2,
                    operateur="pilote",
                )
                Parrainage.objects.create(
                    evenement=event,
                    filleul=filleul,
                    parrain=parrain3,
                    niveau=3,
                    operateur="pilote",
                )

                JournalAudit.enregistrer(event, "tirage", "pilote", {
                    "filleul": f"{filleul.prenom} {filleul.nom}",
                    "parrain2A": f"{parrain2.prenom} {parrain2.nom}",
                    "parrain3A": f"{parrain3.prenom} {parrain3.nom}",
                })

            parrain2_d = map_etudiant(parrain2)
            parrain3_d = map_etudiant(parrain3)

            tirage = {
                "filleul": map_etudiant(filleul),
                "parrain2": parrain2_d,
                "parrain3": parrain3_d,
                "indices2": [x for x in [parrain2.indice1, parrain2.indice2, parrain2.indice3] if x],
                "indices3": [x for x in [parrain3.indice1, parrain3.indice2, parrain3.indice3] if x],
            }

            broadcast("tirage:execute", {"tirage": tirage})
            stats = calculer_stats()
            broadcast("stats:update", stats)

            return Response(tirage)

        except Exception as e:
            msg = str(e)
            s = 409 if msg in ("urne vide",) or msg.startswith("Nouveau") or msg.startswith("Aucun") else 500
            return Response({"error": msg}, status=s)


# ---------------------------------------------------------------------------
# POST /api/tirage/annuler/
# ---------------------------------------------------------------------------

class TirageAnnulerView(APIView):
    def post(self, request):
        parrainage_id = request.data.get("parrainageId", "").strip()
        motif = request.data.get("motif", "").strip()
        if not parrainage_id:
            return Response({"error": "parrainageId requis"}, status=400)

        try:
            p = Parrainage.objects.get(pk=parrainage_id)
        except Parrainage.DoesNotExist:
            return Response({"error": "Parrainage introuvable"}, status=404)

        p.annule = True
        p.motif_annulation = motif
        p.date_annulation = timezone.now()
        p.save()

        # Remettre tire=False sur le filleul si plus aucun parrainage actif
        actifs = Parrainage.objects.filter(filleul=p.filleul, annule=False).count()
        if actifs == 0:
            p.filleul.tire = False
            p.filleul.save(update_fields=["tire"])

        event = get_evenement_actif()
        JournalAudit.enregistrer(event, "annulation", "pilote", {
            "parrainageId": parrainage_id, "motif": motif
        })
        stats = calculer_stats()
        broadcast("stats:update", stats)
        return Response({"ok": True})


# ---------------------------------------------------------------------------
# POST /api/tirage/reinitialiser/
# ---------------------------------------------------------------------------

class TirageReinitialiserView(APIView):
    def post(self, request):
        event = get_evenement_actif()
        nb_parrainages = Parrainage.objects.all().count()
        Parrainage.objects.all().delete()
        Etudiant.objects.filter(tire=True).update(tire=False)
        Jeton.objects.filter(utilise=True).update(utilise=False)

        if event:
            event.statut = "preparation"
            event.save(update_fields=["statut"])
            JournalAudit.enregistrer(event, "reinitialisation", "pilote", {
                "parrainages_supprimes": nb_parrainages
            })

        stats = calculer_stats()
        broadcast("stats:update", stats)
        broadcast("tirage:reset", {})
        return Response({"ok": True, "parrainages_supprimes": nb_parrainages})


# ---------------------------------------------------------------------------
# POST /api/urnes/
# ---------------------------------------------------------------------------

class UrnesView(APIView):
    def post(self, request):
        event = get_evenement_actif()
        if not event:
            return Response({"error": "Aucun événement actif"}, status=400)

        empreinte = generer_toutes_urnes(event)
        event.urnes_generees = True
        event.empreinte_urnes = empreinte
        event.save(update_fields=["urnes_generees", "empreinte_urnes"])

        JournalAudit.enregistrer(event, "urne_generee", "pilote", {"empreinte": empreinte})
        stats = calculer_stats()
        broadcast("stats:update", stats)
        return Response({"ok": True, "empreinte": empreinte})


# ---------------------------------------------------------------------------
# GET /api/binomes/
# ---------------------------------------------------------------------------

class BinomesView(APIView):
    def get(self, request):
        rows = (
            Parrainage.objects
            .filter(annule=False)
            .select_related("filleul", "filleul__filiere", "parrain", "parrain__filiere")
            .order_by("-date_tirage")
        )
        data = [
            {
                "id": r.id,
                "filleul": map_etudiant(r.filleul),
                "parrain": map_etudiant(r.parrain),
                "niveau": r.niveau,
                "dateTirage": r.date_tirage.isoformat() if r.date_tirage else timezone.now().isoformat(),
                "operateur": r.operateur,
                "surprise": r.surprise,
                "annule": r.annule,
            }
            for r in rows
        ]
        return Response(data)


# ---------------------------------------------------------------------------
# POST /api/import/
# ---------------------------------------------------------------------------

class ImportView(APIView):
    def post(self, request):
        csv_text = request.data.get("csv", "").strip()
        if not csv_text:
            return Response({"error": "csv requis"}, status=400)

        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        if not rows:
            return Response({"error": "CSV vide"}, status=400)

        start = 1 if rows and rows[0] and rows[0][0].strip().lower() == "nom" else 0

        def identity_key(nom, prenom, filiere_code, niveau):
            def normalize(value):
                ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
                return " ".join(ascii_value.casefold().split())
            return normalize(nom), normalize(prenom), filiere_code, niveau

        incoming = []
        for line_number, row in enumerate(rows[start:], start=start + 1):
            if len(row) < 4 or not any(cell.strip() for cell in row):
                continue
            nom, prenom, filiere_code = (cell.strip() for cell in row[:3])
            try:
                niveau = int(row[3].strip())
            except ValueError:
                return Response({"error": f"Niveau invalide à la ligne {line_number}"}, status=400)
            if not nom or not prenom or not filiere_code or niveau not in [1, 2, 3]:
                return Response({"error": f"Données invalides à la ligne {line_number}"}, status=400)
            incoming.append({
                "nom": nom,
                "prenom": prenom,
                "filiere": filiere_code,
                "niveau": niveau,
                "photo": row[4].strip() if len(row) > 4 else "",
                "telephone": row[5].strip() if len(row) > 5 else "",
                "email": row[6].strip() if len(row) > 6 else "",
                "indice1": row[7].strip() if len(row) > 7 else "",
                "indice2": row[8].strip() if len(row) > 8 else "",
                "indice3": row[9].strip() if len(row) > 9 else "",
            })

        if not incoming:
            return Response({"error": "Aucune ligne étudiant valide"}, status=400)

        event = get_evenement_actif()
        imported = []
        skipped_existing = 0
        with transaction.atomic():
            existing_keys = {
                identity_key(nom, prenom, filiere_code, niveau)
                for nom, prenom, filiere_code, niveau in Etudiant.objects.values_list(
                    "nom", "prenom", "filiere_id", "niveau"
                )
            }
            for student in incoming:
                key = identity_key(student["nom"], student["prenom"], student["filiere"], student["niveau"])
                if key in existing_keys:
                    skipped_existing += 1
                    continue
                filiere_code = student["filiere"]
                Filiere.objects.get_or_create(
                    code=filiere_code,
                    defaults={
                        "libelle": FILIERE_LIBELLE.get(filiere_code, filiere_code),
                        "couleur": FILIERE_COULEUR.get(filiere_code, "#1F7A3A"),
                        "ordre": 0,
                    },
                )
                Etudiant.objects.create(
                    nom=student["nom"],
                    prenom=student["prenom"],
                    filiere_id=filiere_code,
                    niveau=student["niveau"],
                    photo=student["photo"] or None,
                    telephone=student["telephone"] or None,
                    email=student["email"] or None,
                    indice1=student["indice1"] or None,
                    indice2=student["indice2"] or None,
                    indice3=student["indice3"] or None,
                )
                existing_keys.add(key)
                imported.append({"nom": student["nom"], "prenom": student["prenom"], "filiereCode": filiere_code, "niveau": student["niveau"]})

            JournalAudit.enregistrer(event, "import", "pilote", {
                "count": len(imported),
                "skipped_existing": skipped_existing,
                "sample": imported[:5],
            })
        stats = calculer_stats()
        broadcast("stats:update", stats)
        return Response({"ok": True, "count": len(imported), "skipped_existing": skipped_existing})


# ---------------------------------------------------------------------------
# GET /api/export/?format=csv|json
# ---------------------------------------------------------------------------

class ExportView(APIView):
    def get(self, request):
        fmt = request.query_params.get("format", "csv").lower()

        rows = (
            Parrainage.objects
            .filter(annule=False)
            .select_related("filleul", "parrain")
            .order_by("-date_tirage")
        )

        if fmt == "json":
            data = [
                {
                    "id": r.id,
                    "filleul": map_etudiant(r.filleul),
                    "parrain": map_etudiant(r.parrain),
                    "niveau": r.niveau,
                    "dateTirage": r.date_tirage.isoformat() if r.date_tirage else timezone.now().isoformat(),
                    "operateur": r.operateur,
                }
                for r in rows
            ]
            return Response(data)

        # CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "filleul_nom", "filleul_prenom", "filiere",
            "filleul_niveau", "parrain_nom", "parrain_prenom",
            "parrain_niveau", "date_tirage",
        ])
        for r in rows:
            writer.writerow([
                r.filleul.nom, r.filleul.prenom, r.filleul.filiere_id,
                r.filleul.niveau, r.parrain.nom, r.parrain.prenom,
                r.parrain.niveau, r.date_tirage.isoformat() if r.date_tirage else "",
            ])
        content = output.getvalue()
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="amsen_binomes.csv"'
        return response


# ---------------------------------------------------------------------------
# POST /api/controle/ — commandes pilote
# ---------------------------------------------------------------------------

class ControleView(APIView):
    def post(self, request):
        action = request.data.get("action", "").strip()
        event = get_evenement_actif()

        if action == "absent":
            etudiant_id = request.data.get("etudiantId", "")
            absent = bool(request.data.get("absent", True))
            try:
                etu = Etudiant.objects.get(pk=etudiant_id)
                etu.absent = absent
                etu.save(update_fields=["absent"])
                JournalAudit.enregistrer(event, "absent", "pilote", {
                    "etudiantId": etudiant_id, "absent": absent
                })
                stats = calculer_stats()
                broadcast("stats:update", stats)
                return Response({"ok": True})
            except Etudiant.DoesNotExist:
                return Response({"error": "Étudiant introuvable"}, status=404)

        elif action == "filiere":
            filiere = request.data.get("filiere", "").strip()
            if event:
                event.filiere_active = filiere
                event.save(update_fields=["filiere_active"])
            broadcast("filiere:change", {"filiere": filiere})
            return Response({"ok": True})

        elif action == "mode":
            mode = request.data.get("mode", "cartes")
            difficulte = request.data.get("difficulte", None)
            if event:
                event.mode_animation = mode
                if difficulte:
                    event.difficulte = difficulte
                event.save(update_fields=["mode_animation", "difficulte"])
            broadcast("controle", {"commande": "mode", "payload": {"mode": mode, "difficulte": difficulte}})
            return Response({"ok": True})

        elif action == "son":
            son = bool(request.data.get("son", True))
            if event:
                event.son_actif = son
                event.save(update_fields=["son_actif"])
            broadcast("controle", {"commande": "son", "payload": {"son": son}})
            return Response({"ok": True})

        elif action == "demarrer":
            if event:
                event.statut = "en_cours"
                event.save(update_fields=["statut"])
                JournalAudit.enregistrer(event, "demarrer", "pilote", {})
                stats = calculer_stats()
                broadcast("stats:update", stats)
            return Response({"ok": True})

        elif action == "terminer":
            if event:
                event.statut = "termine"
                event.save(update_fields=["statut"])
                JournalAudit.enregistrer(event, "terminer", "pilote", {})
                stats = calculer_stats()
                broadcast("stats:update", stats)
            return Response({"ok": True})

        else:
            return Response({"error": f"Action inconnue : {action}"}, status=400)


# ---------------------------------------------------------------------------
# GET /api/audit/
# ---------------------------------------------------------------------------

class AuditView(APIView):
    def get(self, request):
        rows = JournalAudit.objects.all().order_by("-horodatage")[:200]
        data = [
            {
                "id": r.id,
                "horodatage": r.horodatage.isoformat(),
                "action": r.action,
                "acteur": r.acteur,
                "details": r.details,
            }
            for r in rows
        ]
        return Response(data)

