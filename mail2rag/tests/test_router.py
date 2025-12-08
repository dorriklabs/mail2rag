"""
Tests for RouterService - email routing to workspaces.
"""
import pytest
from unittest.mock import MagicMock, patch


class MockConfig:
    """Mock configuration for RouterService tests."""
    def __init__(self, default_workspace="default-workspace", routing_path=None):
        self.default_workspace = default_workspace
        self.routing_path = routing_path or MagicMock()
        self.routing_path.exists.return_value = False


class TestRouterExplicitWorkspace:
    """Tests for explicit workspace detection in email body."""
    
    def test_router_explicit_workspace(self):
        """Test detection of 'Workspace: xxx' in email body."""
        from services.router import RouterService
        
        config = MockConfig()
        router = RouterService(config)
        
        email_data = {
            "from": "user@example.com",
            "subject": "Some email",
            "body": "Hello,\n\nWorkspace: projet-alpha\n\nContent here."
        }
        
        result = router.determine_workspace(email_data)
        assert result == "projet-alpha"
    
    def test_router_explicit_dossier(self):
        """Test detection of 'Dossier: yyy' in email body."""
        from services.router import RouterService
        
        config = MockConfig()
        router = RouterService(config)
        
        email_data = {
            "from": "user@example.com",
            "subject": "Some email",
            "body": "Bonjour,\n\nDossier : Client Important\n\nContent here."
        }
        
        result = router.determine_workspace(email_data)
        # Should be slugified
        assert result == "client-important"


class TestRouterRules:
    """Tests for routing rules from routing.json."""
    
    def test_router_rule_sender(self):
        """Test routing rule based on sender."""
        from services.router import RouterService
        
        config = MockConfig()
        router = RouterService(config)
        # Manually set rules (bypassing file loading)
        router.rules = [
            {"type": "sender", "value": "boss@company.com", "workspace": "priority"}
        ]
        
        email_data = {
            "from": "The Boss <boss@company.com>",
            "subject": "Important matter",
            "body": "Hello"
        }
        
        result = router.determine_workspace(email_data)
        assert result == "priority"
    
    def test_router_rule_subject(self):
        """Test routing rule based on subject."""
        from services.router import RouterService
        
        config = MockConfig()
        router = RouterService(config)
        router.rules = [
            {"type": "subject", "value": "[URGENT]", "workspace": "urgent-tasks"}
        ]
        
        email_data = {
            "from": "user@example.com",
            "subject": "[URGENT] Please review ASAP",
            "body": "Hello"
        }
        
        result = router.determine_workspace(email_data)
        assert result == "urgent-tasks"
    
    def test_router_rule_domain(self):
        """Test routing rule based on sender domain."""
        from services.router import RouterService
        
        config = MockConfig()
        router = RouterService(config)
        router.rules = [
            {"type": "sender_domain", "value": "client.com", "workspace": "clients"}
        ]
        
        email_data = {
            "from": "John <john@client.com>",
            "subject": "Project update",
            "body": "Hello"
        }
        
        result = router.determine_workspace(email_data)
        assert result == "clients"


class TestRouterDefault:
    """Tests for default workspace fallback."""
    
    def test_router_default_workspace(self):
        """Test fallback to default workspace when no rules match."""
        from services.router import RouterService
        
        config = MockConfig(default_workspace="my-default")
        router = RouterService(config)
        router.rules = [
            {"type": "sender", "value": "specific@example.com", "workspace": "specific"}
        ]
        
        email_data = {
            "from": "random@other.com",
            "subject": "Random email",
            "body": "Hello"
        }
        
        result = router.determine_workspace(email_data)
        assert result == "my-default"


class TestSlugify:
    """Tests for slugification of workspace names."""
    
    def test_slugify_basic(self):
        """Test basic slugification."""
        from services.router import RouterService
        
        config = MockConfig()
        router = RouterService(config)
        
        assert router._slugify("Projet Alpha") == "projet-alpha"
        assert router._slugify("Client : Important") == "client-important"
        assert router._slugify("Été 2024") == "ete-2024"
        assert router._slugify("  Spaces  ") == "spaces"
    
    def test_slugify_accents(self):
        """Test slugification removes accents."""
        from services.router import RouterService
        
        config = MockConfig()
        router = RouterService(config)
        
        assert router._slugify("Café Résumé") == "cafe-resume"
        assert router._slugify("Négociation") == "negociation"
    
    def test_slugify_empty_returns_default(self):
        """Test empty string returns default workspace."""
        from services.router import RouterService
        
        config = MockConfig(default_workspace="fallback")
        router = RouterService(config)
        
        assert router._slugify("") == "fallback"
        assert router._slugify("   ") == "fallback"
