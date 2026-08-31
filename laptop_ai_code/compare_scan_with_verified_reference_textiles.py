import numpy as np

from laptop_ai_code import ai_settings_and_thresholds as settings


def cosine_similarity(first, second):
    first = np.asarray(first, dtype=np.float64).ravel()
    second = np.asarray(second, dtype=np.float64).ravel()

    if first.size == 0 or second.size == 0 or first.size != second.size:
        return 0.0

    lengths = float(np.linalg.norm(first) * np.linalg.norm(second))
    if lengths <= 1e-12:
        return 0.0
    return float(np.dot(first, second) / lengths)


def cosine_similarity_against_bank(scan_embedding, bank):
    if bank.size == 0:
        return np.zeros(0)

    scan_embedding = np.asarray(scan_embedding, dtype=np.float64).ravel()
    bank = np.asarray(bank, dtype=np.float64)

    scan_length = np.linalg.norm(scan_embedding)
    bank_lengths = np.linalg.norm(bank, axis=1)
    bottom = bank_lengths * scan_length

    with np.errstate(divide="ignore", invalid="ignore"):
        similarity = np.where(bottom > 1e-12, bank @ scan_embedding / bottom, 0.0)
    return np.nan_to_num(similarity, nan=0.0)


class ReferenceLibrary:
    def __init__(self, entries=None):
        # One entry looks like:
        #   {"textile_id", "label", "embedding", "scan_id", "craft_type",
        #    "verification_level"}
        self.entries = list(entries or [])
        self._rebuild_banks()

    def _rebuild_banks(self):
        self.handmade_entries = [
            entry for entry in self.entries if entry["label"] == "handmade"
        ]
        self.machine_entries = [
            entry for entry in self.entries if entry["label"] == "machine"
        ]
        self.handmade_bank = self._stack(self.handmade_entries)
        self.machine_bank = self._stack(self.machine_entries)

    @staticmethod
    def _stack(entries):
        if not entries:
            return np.zeros((0, 0))
        return np.vstack([
            np.asarray(entry["embedding"], dtype=np.float64).ravel()
            for entry in entries
        ])

    def add(self, textile_id, label, embedding, scan_id="", craft_type="",
            verification_level=""):
        self.entries.append({
            "textile_id": textile_id,
            "label": label,
            "embedding": np.asarray(embedding, dtype=np.float64).ravel(),
            "scan_id": scan_id,
            "craft_type": craft_type,
            "verification_level": verification_level,
        })
        self._rebuild_banks()

    @property
    def size(self):
        return len(self.entries)

    @property
    def handmade_count(self):
        return len(self.handmade_entries)

    @property
    def machine_count(self):
        return len(self.machine_entries)

    def _best_matches(self, scan_embedding, entries, bank):
        scan_size = np.asarray(scan_embedding).ravel().size
        if not entries or bank.size == 0 or bank.shape[1] != scan_size:
            return []

        similarity = cosine_similarity_against_bank(scan_embedding, bank)
        best_first = np.argsort(similarity)[::-1][:settings.REFERENCE_TOP_K]

        return [
            {
                "textile_id": entries[position]["textile_id"],
                "scan_id": entries[position]["scan_id"],
                "similarity": float(similarity[position]),
                "craft_type": entries[position]["craft_type"],
                "verification_level": entries[position]["verification_level"],
            }
            for position in best_first
        ]

    def compare(self, scan_embedding):
        """Compare one scan embedding with both banks."""
        reasons = []

        if self.size == 0:
            return {
                "nearest_handmade": None,
                "handmade_similarity": None,
                "nearest_machine": None,
                "machine_similarity": None,
                "top_handmade": [],
                "top_machine": [],
                "out_of_domain": True,
                "reasons": ["reference_library_empty"],
            }

        scan_embedding = np.asarray(scan_embedding, dtype=np.float64).ravel()
        if scan_embedding.size == 0:
            return {
                "nearest_handmade": None,
                "handmade_similarity": None,
                "nearest_machine": None,
                "machine_similarity": None,
                "top_handmade": [],
                "top_machine": [],
                "out_of_domain": True,
                "reasons": ["scan_embedding_missing"],
            }

        top_handmade = self._best_matches(
            scan_embedding, self.handmade_entries, self.handmade_bank
        )
        top_machine = self._best_matches(
            scan_embedding, self.machine_entries, self.machine_bank
        )

        if not top_handmade:
            reasons.append("no_handmade_references")
        if not top_machine:
            reasons.append("no_machine_references")

        best_handmade = top_handmade[0] if top_handmade else None
        best_machine = top_machine[0] if top_machine else None

        best_similarity = max(
            best_handmade["similarity"] if best_handmade else -1.0,
            best_machine["similarity"] if best_machine else -1.0,
        )

        out_of_domain = best_similarity < settings.OUT_OF_DOMAIN_SIMILARITY
        if out_of_domain:
            reasons.append("out_of_domain")

        return {
            "nearest_handmade": best_handmade["textile_id"] if best_handmade else None,
            "handmade_similarity": (
                best_handmade["similarity"] if best_handmade else None
            ),
            "nearest_machine": best_machine["textile_id"] if best_machine else None,
            "machine_similarity": (
                best_machine["similarity"] if best_machine else None
            ),
            "top_handmade": top_handmade,
            "top_machine": top_machine,
            "out_of_domain": out_of_domain,
            "reasons": reasons,
        }


    def to_arrays(self):
        """The form stored as reference_embeddings.npz inside a model folder."""
        return {
            "embeddings": self._stack(self.entries),
            "textile_ids": np.array(
                [entry["textile_id"] for entry in self.entries], dtype=object),
            "labels": np.array(
                [entry["label"] for entry in self.entries], dtype=object),
            "scan_ids": np.array(
                [entry["scan_id"] for entry in self.entries], dtype=object),
            "craft_types": np.array(
                [entry["craft_type"] for entry in self.entries], dtype=object),
            "verification_levels": np.array(
                [entry["verification_level"] for entry in self.entries],
                dtype=object),
        }

    @classmethod
    def from_arrays(cls, payload):
        if payload is None:
            return cls([])

        embeddings = np.asarray(payload["embeddings"], dtype=np.float64)
        textile_ids = list(payload["textile_ids"])
        labels = list(payload["labels"])
        scan_ids = list(payload.get("scan_ids", [""] * len(textile_ids)))
        craft_types = list(payload.get("craft_types", [""] * len(textile_ids)))
        levels = list(payload.get("verification_levels", [""] * len(textile_ids)))

        entries = []
        for position in range(len(textile_ids)):
            entries.append({
                "textile_id": str(textile_ids[position]),
                "label": str(labels[position]),
                "embedding": embeddings[position],
                "scan_id": str(scan_ids[position]),
                "craft_type": str(craft_types[position]),
                "verification_level": str(levels[position]),
            })
        return cls(entries)
