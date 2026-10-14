"""Django app — models AMSEN Parrainage"""
import secrets
import hashlib
from django.db import models


class Filiere(models.Model):
    code = models.CharField(max_length=20, primary_key=True)
    libelle = models.CharField(max_length=100)
    couleur = models.CharField(max_length=20, default="#1F7A3A")
    ordre = models.IntegerField(default=0)

    class Meta:
        ordering = ["ordre"]
        verbose_name = "Filière"

    def __str__(self):
        return self.code


class Etudiant(models.Model):
    NIVEAU_CHOICES = [(1, "Nouveau"), (2, "Parrain 2A"), (3, "Parrain 3A")]

    id = models.CharField(max_length=36, primary_key=True, default=secrets.token_urlsafe)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    filiere = models.ForeignKey(Filiere, on_delete=models.PROTECT, related_name="etudiants")
    niveau = models.IntegerField(choices=NIVEAU_CHOICES)
    photo = models.CharField(max_length=500, null=True, blank=True)
    telephone = models.CharField(max_length=30, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    indice1 = models.CharField(max_length=200, null=True, blank=True)
    indice2 = models.CharField(max_length=200, null=True, blank=True)
    indice3 = models.CharField(max_length=200, null=True, blank=True)
    qrcode = models.CharField(max_length=500, null=True, blank=True)
    absent = models.BooleanField(default=False)
    tire = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["filiere", "niveau"]),
        ]
        verbose_name = "Étudiant"

    def __str__(self):
        return f"{self.prenom} {self.nom} (N{self.niveau})"


class Evenement(models.Model):
    STATUT_CHOICES = [
        ("preparation", "Préparation"),
        ("en_cours", "En cours"),
        ("termine", "Terminé"),
    ]
    MODE_CHOICES = [
        ("cartes", "Cartes"),
        ("roulette", "Roulette"),
        ("coffre", "Coffre"),
        ("constellation", "Constellation"),
        ("des", "Dés"),
    ]
    DIFFICULTE_CHOICES = [
        ("facile", "Facile"),
        ("moyen", "Moyen"),
        ("difficile", "Difficile"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=secrets.token_urlsafe)
    nom = models.CharField(max_length=200)
    date = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default="preparation")
    mode_animation = models.CharField(max_length=20, choices=MODE_CHOICES, default="cartes")
    difficulte = models.CharField(max_length=20, choices=DIFFICULTE_CHOICES, default="moyen")
    filiere_active = models.CharField(max_length=20, default="AS")
    parrain_surprise = models.BooleanField(default=False)
    son_actif = models.BooleanField(default=True)
    urnes_generees = models.BooleanField(default=False)
    empreinte_urnes = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Événement"

    def __str__(self):
        return f"{self.nom} ({self.statut})"


class Jeton(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=secrets.token_urlsafe)
    evenement = models.ForeignKey(Evenement, on_delete=models.CASCADE, related_name="jetons")
    filiere = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name="jetons")
    niveau = models.IntegerField()
    parrain = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name="jetons")
    utilise = models.BooleanField(default=False)
    ordre = models.IntegerField(default=0)
    tier = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["filiere", "niveau", "utilise"]),
            models.Index(fields=["evenement"]),
            models.Index(fields=["filiere", "niveau", "tier", "utilise"]),
        ]
        verbose_name = "Jeton"

    def __str__(self):
        return f"Jeton {self.id[:8]} — {self.parrain} (tier {self.tier})"


class Parrainage(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=secrets.token_urlsafe)
    evenement = models.ForeignKey(Evenement, on_delete=models.CASCADE, related_name="parrainages")
    filleul = models.ForeignKey(
        Etudiant, on_delete=models.PROTECT, related_name="filleul_de"
    )
    parrain = models.ForeignKey(
        Etudiant, on_delete=models.PROTECT, related_name="parrain_de"
    )
    niveau = models.IntegerField()
    date_tirage = models.DateTimeField(auto_now_add=True)
    operateur = models.CharField(max_length=50, default="pilote")
    surprise = models.BooleanField(default=False)
    annule = models.BooleanField(default=False)
    motif_annulation = models.TextField(null=True, blank=True)
    date_annulation = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["filleul"]),
            models.Index(fields=["parrain"]),
            models.Index(fields=["evenement"]),
        ]
        verbose_name = "Parrainage"

    def __str__(self):
        return f"{self.filleul} ← {self.parrain} (N{self.niveau})"


class JournalAudit(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=secrets.token_urlsafe)
    evenement = models.ForeignKey(
        Evenement, on_delete=models.SET_NULL, null=True, blank=True, related_name="audits"
    )
    horodatage = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=50)
    acteur = models.CharField(max_length=50, default="pilote")
    details = models.TextField()
    empreinte = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["evenement"])]
        ordering = ["-horodatage"]
        verbose_name = "Audit"

    @classmethod
    def enregistrer(cls, evenement, action, acteur, details_dict):
        import json
        from datetime import datetime, timezone

        horodatage = datetime.now(timezone.utc).isoformat()
        details_str = json.dumps(details_dict, ensure_ascii=False)
        raw = f"{action}|{acteur}|{details_str}|{horodatage}"
        empreinte = hashlib.sha256(raw.encode()).hexdigest()
        return cls.objects.create(
            evenement=evenement,
            action=action,
            acteur=acteur,
            details=details_str,
            empreinte=empreinte,
        )

