from django.urls import path
from . import views

urlpatterns = [
    # Stats globales
    path("stats/", views.StatsView.as_view(), name="stats"),
    path("portraits/", views.PortraitsView.as_view(), name="portraits"),

    # Événements
    path("evenements/", views.EvenementView.as_view(), name="evenements"),

    # Tirage
    path("tirage/prochain/", views.TirageProchainView.as_view(), name="tirage-prochain"),
    path("tirage/executer/", views.TirageExecuterView.as_view(), name="tirage-executer"),
    path("tirage/annuler/", views.TirageAnnulerView.as_view(), name="tirage-annuler"),
    path("tirage/reinitialiser/", views.TirageReinitialiserView.as_view(), name="tirage-reinitialiser"),

    # Urnes
    path("urnes/", views.UrnesView.as_view(), name="urnes"),

    # Binômes (résultats)
    path("binomes/", views.BinomesView.as_view(), name="binomes"),

    # Import / Export
    path("import/", views.ImportView.as_view(), name="import"),
    path("export/", views.ExportView.as_view(), name="export"),

    # Contrôle pilote
    path("controle/", views.ControleView.as_view(), name="controle"),

    # Audit
    path("audit/", views.AuditView.as_view(), name="audit"),
]

