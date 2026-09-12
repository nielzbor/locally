import math
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class TransactionExtraite(BaseModel):
    """Représente une transaction unique nettoyée et enrichie."""

    # Métadonnées et dates
    date: datetime = Field(..., description="Date de comptabilisation de l'opération")
    valeur: datetime | None = Field(None, description="Date de valeur de l'opération")
    carte_date_reelle: datetime | None = Field(
        None, description="Date d'achat réelle pour les opérations carte"
    )
    page_number: int = Field(..., ge=1, description="Numéro de page du relevé PDF")

    # Types et classification brute
    tx_type: Literal[
        "CARTE",
        "PRELEVEMENT",
        "VIREMENT",
        "RETROCESSION",
        "CHEQUE",
        "RETRAIT_DAB",
        "COMMISSION",
        "AUTRE",
    ] = Field(..., description="Type de transaction identifié")

    # Identifiants SEPA et détails techniques
    sepa_emetteur: str | None = Field(
        None, description="Identifiant créancier SEPA (ICS)"
    )
    sepa_mandat: str | None = Field(None, description="Référence Mandat (RUM)")
    sepa_reference: str | None = Field(None, description="Référence de paiement SEPA")
    motif: str | None = Field(
        None, description="Motif ou détail complémentaire de la transaction"
    )

    # Libellé à traiter par le LLM (ou pas)
    raw_merchant_text: str | None = Field(
        ..., description="Texte brut nettoyé destiné à l'extraction du marchand"
    )

    # Montants (Validation d'exclusivité Débit/Crédit)
    debit: float | None = Field(None, ge=0.0, description="Montant du débit en EUR")
    credit: float | None = Field(None, ge=0.0, description="Montant du crédit en EUR")

    @field_validator("credit")
    @classmethod
    def check_debit_credit_exclusive(cls, v, info):
        """Vérifie qu'une transaction n'est pas à la fois un débit et un crédit."""
        debit = info.data.get("debit")
        if debit is not None and v is not None:
            raise ValueError(
                "Une transaction ne peut pas contenir à la fois un débit et un crédit."
            )
        if debit is None and v is None:
            raise ValueError("Une transaction doit avoir soit un débit soit un crédit.")
        return v


class ReleveBancaire(BaseModel):
    """Conteneur global du relevé bancaire avec ses métadonnées et assertions."""

    filename: str
    statement_date: str
    solde_initial: float | None = Field(None, ge=0.0)
    total_debit: float | None = Field(None, ge=0.0)
    total_credit: float | None = Field(None, ge=0.0)
    solde_final: float | None = None
    transactions: list[TransactionExtraite]

    @model_validator(mode="after")
    def check_mathematical_reconciliation(self) -> ReleveBancaire:
        """Vérifie la cohérence comptable du relevé bancaire."""
        # 1. Vérification : Solde Initial + Total Crédit - Total Débit == Solde Final
        if (
            self.solde_initial is not None
            and self.total_credit is not None
            and self.total_debit is not None
            and self.solde_final is not None
        ):
            calculated_final = self.solde_initial + self.total_credit - self.total_debit
            if not math.isclose(calculated_final, self.solde_final, abs_tol=0.01):
                raise ValueError(
                    f"Incohérence des soldes : solde_initial ({self.solde_initial}) + "
                    f"total_credit ({self.total_credit}) - total_debit ({self.total_debit}) = "
                    f"{calculated_final:.2f}, mais solde_final déclaré = {self.solde_final}"
                )

        # 2. Vérification : Somme des débits des transactions == Total Débit déclaré
        if self.total_debit is not None and self.transactions:
            sum_debits = sum(
                tx.debit for tx in self.transactions if tx.debit is not None
            )
            if not math.isclose(sum_debits, self.total_debit, abs_tol=0.01):
                raise ValueError(
                    f"Incohérence de la somme des débits : somme calculée = {sum_debits:.2f}, "
                    f"total_debit déclaré = {self.total_debit}"
                )

        # 3. Vérification : Somme des crédits des transactions == Total Crédit déclaré
        if self.total_credit is not None and self.transactions:
            sum_credits = sum(
                tx.credit for tx in self.transactions if tx.credit is not None
            )
            if not math.isclose(sum_credits, self.total_credit, abs_tol=0.01):
                raise ValueError(
                    f"Incohérence de la somme des crédits : somme calculée = {sum_credits:.2f}, "
                    f"total_credit déclaré = {self.total_credit}"
                )

        return self


class CategorieDepense(str, Enum):
    ALIMENTATION = "Alimentation & Courses"
    LOGEMENT = "Logement & Charges"
    TRANSPORT = "Transports & Véhicule"
    ABONNEMENT = "Abonnements & Services"
    LOISIRS = "Loisirs & Sorties"
    SANTE = "Santé"
    REVENU = "Revenu & Virement entrant"
    AUTRE = "Autre / Non classé"


class TransactionCategorisee(BaseModel):
    id: int = Field(..., description="L'index de la transaction")
    marchand_clean: str = Field(..., description="Nom propre et nettoyé du commerçant")
    categorie: CategorieDepense = Field(..., description="La catégorie retenue")
    # justification: Optional[str] = Field(None, description="Courte explication si cas ambigu")


class BatchCategorisation(BaseModel):
    transactions: list[TransactionCategorisee]
