"""
Sérialiseurs DRF — AMSEN Parrainage
"""
from rest_framework import serializers
from .models import Filiere, Etudiant, Evenement, Parrainage, JournalAudit


class FiliereSerializer(serializers.ModelSerializer):
    class Meta:
        model = Filiere
        fields = ["code", "libelle", "couleur", "ordre"]


class EtudiantSerializer(serializers.ModelSerializer):
    filiere_code = serializers.CharField(source="filiere_id")

    class Meta:
        model = Etudiant
        fields = [
            "id", "nom", "prenom", "filiere_code", "niveau",
            "photo", "telephone", "email",
            "indice1", "indice2", "indice3",
            "absent", "tire",
        ]


class EvenementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Evenement
        fields = [
            "id", "nom", "date", "statut",
            "mode_animation", "difficulte", "filiere_active",
            "parrain_surprise", "son_actif",
            "urnes_generees", "empreinte_urnes",
        ]


class ParrainageSerializer(serializers.ModelSerializer):
    filleul = EtudiantSerializer(read_only=True)
    parrain = EtudiantSerializer(read_only=True)

    class Meta:
        model = Parrainage
        fields = [
            "id", "filleul", "parrain", "niveau",
            "date_tirage", "operateur", "surprise", "annule",
        ]


class AuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalAudit
        fields = ["id", "horodatage", "action", "acteur", "details"]

