"""
Module de chunking intelligent pour RAG Proxy.

Fournit des stratégies de découpage de texte optimisées pour la recherche RAG,
avec préservation des frontières de phrases et métadonnées enrichies.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """
    Représente un chunk de texte avec ses métadonnées.
    
    Attributes:
        text: Contenu textuel du chunk
        index: Position du chunk dans la séquence (0-indexed)
        total_chunks: Nombre total de chunks dans le document
        metadata: Métadonnées additionnelles (source, date, etc.)
        char_start: Position de début du chunk dans le texte original (optionnel)
        char_end: Position de fin du chunk dans le texte original (optionnel)
    """
    text: str
    index: int
    total_chunks: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit le chunk en dictionnaire pour sérialisation."""
        return {
            "text": self.text,
            "index": self.index,
            "total_chunks": self.total_chunks,
            "metadata": self.metadata,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


class RecursiveTextSplitter:
    """
    Splitter récursif qui découpe le texte en respectant la hiérarchie :
    Paragraphes → Phrases → Mots
    
    Préserve les frontières de phrases autant que possible et ajoute un overlap
    configurable pour maintenir le contexte entre chunks.
    """
    
    # Séparateurs par ordre de priorité (du plus grand au plus petit)
    DEFAULT_SEPARATORS = [
        "\n\n",  # Paragraphes
        "\n",    # Lignes
        ". ",    # Phrases (point suivi d'espace)
        "! ",    # Phrases exclamatives
        "? ",    # Phrases interrogatives
        "; ",    # Points-virgules
        ", ",    # Virgules
        " ",     # Espaces
        ""       # Caractères (fallback)
    ]
    
    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        separators: Optional[List[str]] = None,
    ):
        """
        Initialise le splitter.
        
        Args:
            chunk_size: Taille maximale d'un chunk en caractères
            chunk_overlap: Nombre de caractères de chevauchement entre chunks
            separators: Liste de séparateurs personnalisés (ordre de priorité)
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size doit être > 0")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap doit être >= 0")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap doit être < chunk_size")
        
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or self.DEFAULT_SEPARATORS
        
        logger.debug(
            f"RecursiveTextSplitter initialized: size={chunk_size}, overlap={chunk_overlap}"
        )
    
    def split_text(self, text: str) -> List[str]:
        """
        Découpe le texte en chunks.
        
        Args:
            text: Texte à découper
            
        Returns:
            Liste de strings (chunks)
        """
        if not text or not text.strip():
            return []
        
        # Nettoyer légèrement le texte (normaliser espaces multiples)
        text = re.sub(r' +', ' ', text)
        
        # Si le texte est déjà plus petit que chunk_size, retourner tel quel
        if len(text) <= self.chunk_size:
            return [text]
        
        # Découpage récursif
        return self._recursive_split(text, self.separators)
    
    def _recursive_split(self, text: str, separators: List[str]) -> List[str]:
        """
        Découpe récursivement le texte en utilisant les séparateurs par ordre de priorité.
        
        Args:
            text: Texte à découper
            separators: Liste de séparateurs à essayer
            
        Returns:
            Liste de chunks
        """
        if not separators:
            # Fallback : découpe brutale par caractères
            return self._split_by_chars(text)
        
        # Prendre le premier séparateur
        separator = separators[0]
        remaining_separators = separators[1:]
        
        # Découper par ce séparateur
        if separator == "":
            # Cas spécial : découpe par caractères
            return self._split_by_chars(text)
        
        splits = text.split(separator)
        
        # Reconstruire les morceaux avec le séparateur
        chunks = []
        current_chunk = ""
        
        for i, split in enumerate(splits):
            # Réajouter le séparateur (sauf pour le dernier)
            piece = split + (separator if i < len(splits) - 1 else "")
            
            # Si le morceau actuel + ce morceau dépasse chunk_size
            if len(current_chunk) + len(piece) > self.chunk_size:
                if current_chunk:
                    # Sauvegarder le chunk actuel
                    chunks.append(current_chunk.strip())
                    
                    # Commencer nouveau chunk avec overlap
                    overlap_start = max(0, len(current_chunk) - self.chunk_overlap)
                    current_chunk = current_chunk[overlap_start:] + piece
                else:
                    # Le morceau seul est trop grand, découper plus finement
                    if len(piece) > self.chunk_size:
                        sub_chunks = self._recursive_split(piece, remaining_separators)
                        chunks.extend(sub_chunks[:-1])
                        current_chunk = sub_chunks[-1] if sub_chunks else ""
                    else:
                        current_chunk = piece
            else:
                current_chunk += piece
        
        # Ajouter le dernier chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _split_by_chars(self, text: str) -> List[str]:
        """
        Découpe brutale par caractères (fallback).
        
        Args:
            text: Texte à découper
            
        Returns:
            Liste de chunks
        """
        chunks = []
        start = 0
        
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunks.append(text[start:end])
            start = end - self.chunk_overlap if end < len(text) else end
        
        return chunks



class MarkdownHeaderSplitter:
    """
    Découpe le texte en fonction des en-têtes Markdown (# Titre, ## Sous-titre)
    et conserve la hiérarchie pour chaque bloc de texte.
    """
    def __init__(self, headers_to_split_on: Optional[List[Tuple[str, str]]] = None):
        if headers_to_split_on is None:
            self.headers_to_split_on = [
                ("#", "H1"),
                ("##", "H2"),
                ("###", "H3"),
                ("####", "H4"),
                ("#####", "H5"),
                ("######", "H6"),
            ]
        else:
            self.headers_to_split_on = headers_to_split_on

    def split_text(self, text: str) -> List[Dict[str, Any]]:
        lines = text.split('\n')
        chunks = []
        current_content = []
        current_metadata = {}
        
        sorted_headers = sorted(self.headers_to_split_on, key=lambda x: len(x[0]), reverse=True)
        
        for line in lines:
            header_match = None
            for sep, name in sorted_headers:
                stripped_line = line.strip()
                if stripped_line.startswith(sep):
                    next_char_idx = len(sep)
                    if next_char_idx >= len(stripped_line) or stripped_line[next_char_idx] in (" ", "*", "~", "_", "<"):
                        raw_text = stripped_line[next_char_idx:].strip()
                        # Nettoyer universellement tout type de formatage Markdown (*, ~, _, <, >)
                        clean_text = re.sub(r'[*~_<]+(.*?)[*~_>]+', r'\1', raw_text)
                        clean_text = clean_text.strip()
                        header_match = (sep, name, clean_text)
                        break
            
            if header_match:
                sep, name, header_text = header_match
                content_str = '\n'.join(current_content).strip()
                if content_str:
                    chunks.append({"text": content_str, "metadata": current_metadata.copy()})
                current_content = []
                
                sep_level = len(sep)
                keys_to_remove = []
                for k in current_metadata.keys():
                    for s, n in sorted_headers:
                        if n == k and len(s) >= sep_level:
                            keys_to_remove.append(k)
                for k in keys_to_remove:
                    current_metadata.pop(k, None)
                
                current_metadata[name] = header_text
            else:
                current_content.append(line)
                
        content_str = '\n'.join(current_content).strip()
        if content_str or current_metadata:
            chunks.append({"text": content_str, "metadata": current_metadata.copy()})
            
        return chunks

class TextChunker:
    """
    Classe principale pour le chunking de documents.
    
    Fournit une interface de haut niveau pour découper des documents
    avec métadonnées enrichies.
    """
    
    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        strategy: str = "recursive",
    ):
        """
        Initialise le chunker.
        
        Args:
            chunk_size: Taille maximale d'un chunk en caractères
            chunk_overlap: Nombre de caractères de chevauchement
            strategy: Stratégie de chunking ("recursive" uniquement pour l'instant)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.strategy = strategy
        
        self.recursive_splitter = RecursiveTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        self.markdown_splitter = MarkdownHeaderSplitter()
        
        logger.info(
            f"TextChunker initialized: strategy={strategy}, "
            f"chunk_size={chunk_size}, overlap={chunk_overlap}"
        )
    
    def chunk_text(
        self,
        text: str,
        base_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Chunk]:
        """
        Découpe un texte en chunks avec métadonnées.
        
        Args:
            text: Texte à découper
            base_metadata: Métadonnées de base à ajouter à tous les chunks
            
        Returns:
            Liste de Chunk objects
        """
        if not text or not text.strip():
            logger.warning("Texte vide fourni au chunker")
            return []
        
        # Choix de la stratégie
        final_text_chunks = []
        if self.strategy == "markdown":
            md_chunks = self.markdown_splitter.split_text(text)
            for md_chunk in md_chunks:
                md_text = md_chunk["text"]
                md_meta = md_chunk["metadata"]
                
                # Ignorer les blocs vides sans métadonnées intéressantes
                if not md_text and not md_meta:
                    continue
                    
                breadcrumb = " > ".join(md_meta.values())
                context_prefix = f"[Contexte: {breadcrumb}]\n" if breadcrumb else ""
                
                # Si pas de texte mais on a un contexte, on ignore
                if not md_text:
                    continue
                    
                sub_chunks = self.recursive_splitter.split_text(md_text)
                for sc in sub_chunks:
                    # On évite de dupliquer le préfixe s'il est déjà au début (au cas où)
                    if context_prefix and not sc.startswith(context_prefix):
                        final_chunk_text = context_prefix + sc
                    else:
                        final_chunk_text = sc
                    
                    # Fusion des métadonnées markdown avec base
                    combo_meta = {**md_meta}
                    final_text_chunks.append((final_chunk_text, combo_meta))
        else:
            splits = self.recursive_splitter.split_text(text)
            final_text_chunks = [(s, {}) for s in splits]

        total_chunks = len(final_text_chunks)
        logger.debug(f"Texte découpé en {total_chunks} chunks avec la stratégie {self.strategy}")
        
        chunks = []
        char_position = 0
        base_metadata = base_metadata or {}
        
        for i, (chunk_text, md_meta) in enumerate(final_text_chunks):
            start_ext = max(0, char_position - 400)
            end_ext = min(len(text), char_position + len(chunk_text) + 400)
            extended_text = text[start_ext:end_ext]
            
            chunk_metadata = {
                **base_metadata,
                **md_meta,
                "chunk_index": i,
                "chunk_total": total_chunks,
                "chunk_size": len(chunk_text),
                "extended_text": extended_text,
            }
            
            chunk = Chunk(
                text=chunk_text,
                index=i,
                total_chunks=total_chunks,
                metadata=chunk_metadata,
                char_start=char_position,
                char_end=char_position + len(chunk_text),
            )
            
            chunks.append(chunk)
            char_position += len(chunk_text) - self.chunk_overlap
        
        return chunks
    
    def chunk_document(
        self,
        text: str,
        metadata: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Découpe un document et retourne des dicts prêts pour l'indexation.
        
        Args:
            text: Contenu du document
            metadata: Métadonnées du document (filename, subject, date, etc.)
            
        Returns:
            Liste de dicts avec format {text, metadata} où metadata inclut char_start et char_end
        """
        chunks = self.chunk_text(text, base_metadata=metadata)
        
        return [
            {
                "text": chunk.text,
                "metadata": {
                    **chunk.metadata,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                },
            }
            for chunk in chunks
        ]
