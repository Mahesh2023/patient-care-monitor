"""
Accessibility Utilities
======================
Accessibility improvements for the application.

Features:
- ARIA label generation
- Keyboard navigation helpers
- Screen reader support
- Focus management
- Skip-to-content links
"""

import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class ARIAGenerator:
    """Generate ARIA labels and attributes for UI components."""
    
    @staticmethod
    def generate_label(component_type: str, content: str, context: Optional[str] = None) -> str:
        """
        Generate ARIA label for a component.
        
        Args:
            component_type: Type of component (button, input, etc.)
            content: Content of the component
            context: Additional context for the label
            
        Returns:
            ARIA label string
        """
        labels = {
            "button": f"Button: {content}",
            "input": f"Input field for {content}",
            "select": f"Dropdown selection for {content}",
            "checkbox": f"Checkbox for {content}",
            "radio": f"Radio button for {content}",
            "link": f"Link to {content}",
            "menu": f"Menu: {content}",
            "dialog": f"Dialog: {content}",
            "alert": f"Alert: {content}"
        }
        
        base_label = labels.get(component_type, f"{component_type}: {content}")
        
        if context:
            return f"{base_label} - {context}"
        
        return base_label
    
    @staticmethod
    def generate_description(content: str) -> str:
        """
        Generate ARIA description.
        
        Args:
            content: Content to describe
            
        Returns:
            ARIA description string
        """
        return f"Description: {content}"
    
    @staticmethod
    def generate_live_region(politeness: str = "polite") -> Dict[str, str]:
        """
        Generate ARIA live region attributes.
        
        Args:
            politeness: Politeness level (polite, assertive, off)
            
        Returns:
            Dictionary of ARIA attributes
        """
        return {
            "aria-live": politeness,
            "aria-atomic": "true"
        }
    
    @staticmethod
    def generate_role(role: str) -> Dict[str, str]:
        """
        Generate ARIA role attribute.
        
        Args:
            role: ARIA role
            
        Returns:
            Dictionary with role attribute
        """
        return {"role": role}


class KeyboardNavigation:
    """Keyboard navigation helpers."""
    
    @staticmethod
    def generate_shortcuts(component_id: str, shortcuts: List[str]) -> Dict[str, str]:
        """
        Generate keyboard shortcut attributes.
        
        Args:
            component_id: Component identifier
            shortcuts: List of keyboard shortcuts
            
        Returns:
            Dictionary with keyboard navigation attributes
        """
        return {
            "tabindex": "0",
            "data-shortcuts": ",".join(shortcuts),
            "aria-keyshortcuts": ",".join(shortcuts)
        }
    
    @staticmethod
    def generate_focus_trap(container_id: str) -> Dict[str, str]:
        """
        Generate focus trap attributes for modal dialogs.
        
        Args:
            container_id: Container identifier
            
        Returns:
            Dictionary with focus trap attributes
        """
        return {
            "role": "dialog",
            "aria-modal": "true",
            "data-focus-trap": "true"
        }
    
    @staticmethod
    def get_navigation_order(elements: List[str]) -> List[str]:
        """
        Get logical tab order for elements.
        
        Args:
            elements: List of element identifiers
            
        Returns:
            Ordered list of element identifiers
        """
        # Simple implementation - can be enhanced with semantic ordering
        return elements


class ScreenReaderSupport:
    """Screen reader support utilities."""
    
    @staticmethod
    def generate_announcement(message: str, priority: str = "polite") -> Dict[str, str]:
        """
        Generate screen reader announcement.
        
        Args:
            message: Message to announce
            priority: Announcement priority (polite, assertive)
            
        Returns:
            Dictionary with announcement attributes
        """
        return {
            "aria-live": priority,
            "aria-atomic": "true",
            "aria-label": message
        }
    
    @staticmethod
    def hide_from_screen_reader() -> Dict[str, str]:
        """
        Generate attributes to hide element from screen readers.
        
        Returns:
            Dictionary with hidden attributes
        """
        return {
            "aria-hidden": "true"
        }
    
    @staticmethod
    def describe_visual_element(description: str) -> Dict[str, str]:
        """
        Generate description for visual elements.
        
        Args:
            description: Description of visual element
            
        Returns:
            Dictionary with description attributes
        """
        return {
            "aria-describedby": description
        }


class FocusManager:
    """Focus management utilities."""
    
    @staticmethod
    def set_focus(element_id: str) -> str:
        """
        Generate JavaScript to set focus on element.
        
        Args:
            element_id: Element identifier
            
        Returns:
            JavaScript code to set focus
        """
        return f"document.getElementById('{element_id}').focus();"
    
    @staticmethod
    def generate_skip_link(target_id: str, text: str = "Skip to main content") -> str:
        """
        Generate skip-to-content link.
        
        Args:
            target_id: Target element identifier
            text: Link text
            
        Returns:
            HTML for skip link
        """
        return f'<a href="#{target_id}" class="skip-link" tabindex="1">{text}</a>'
    
    @staticmethod
    def generate_focus_indicator() -> Dict[str, str]:
        """
        Generate focus indicator styles.
        
        Returns:
            Dictionary with focus styles
        """
        return {
            "outline": "3px solid #4dabf7",
            "outline-offset": "2px"
        }


class AccessibilityValidator:
    """Validate accessibility compliance."""
    
    @staticmethod
    def check_color_contrast(foreground: str, background: str) -> Dict[str, Any]:
        """
        Check color contrast ratio (WCAG 2.1).
        
        Args:
            foreground: Foreground color (hex)
            background: Background color (hex)
            
        Returns:
            Dictionary with contrast ratio and compliance info
        """
        # Simplified implementation - in production use proper color contrast calculator
        try:
            # Convert hex to RGB
            fg_rgb = tuple(int(foreground.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
            bg_rgb = tuple(int(background.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
            
            # Calculate relative luminance (simplified)
            def get_luminance(rgb):
                r, g, b = rgb
                return 0.2126 * r + 0.7152 * g + 0.0722 * b
            
            l1 = get_luminance(fg_rgb)
            l2 = get_luminance(bg_rgb)
            
            lighter = max(l1, l2)
            darker = min(l1, l2)
            
            contrast_ratio = (lighter + 0.05) / (darker + 0.05)
            
            # WCAG 2.1 compliance
            aa_normal = contrast_ratio >= 4.5
            aa_large = contrast_ratio >= 3.0
            aaa_normal = contrast_ratio >= 7.0
            aaa_large = contrast_ratio >= 4.5
            
            return {
                "contrast_ratio": round(contrast_ratio, 2),
                "wcag_aa_normal": aa_normal,
                "wcag_aa_large": aa_large,
                "wcag_aaa_normal": aaa_normal,
                "wcag_aaa_large": aaa_large,
                "compliant": aa_normal
            }
        except Exception as e:
            logger.error(f"Error checking color contrast: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def check_heading_structure(headings: List[Dict]) -> Dict[str, Any]:
        """
        Check heading structure for proper hierarchy.
        
        Args:
            headings: List of heading dictionaries with level and text
            
        Returns:
            Dictionary with validation results
        """
        errors = []
        warnings = []
        previous_level = 0
        
        for heading in headings:
            level = heading.get("level", 0)
            text = heading.get("text", "")
            
            # Check for skipped levels
            if level > previous_level + 1:
                warnings.append(
                    f"Skipped heading level: h{previous_level} to h{level} in '{text}'"
                )
            
            # Check for proper starting level
            if previous_level == 0 and level != 1:
                errors.append(
                    f"First heading should be h1, found h{level} in '{text}'"
                )
            
            previous_level = level
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    @staticmethod
    def check_alt_text(images: List[Dict]) -> Dict[str, Any]:
        """
        Check that images have appropriate alt text.
        
        Args:
            images: List of image dictionaries with src and alt
            
        Returns:
            Dictionary with validation results
        """
        missing_alt = []
        decorative = []
        
        for image in images:
            src = image.get("src", "")
            alt = image.get("alt", "")
            
            if not alt:
                missing_alt.append(src)
            elif alt.lower() in ["", "decorative", "null"]:
                decorative.append(src)
        
        return {
            "valid": len(missing_alt) == 0,
            "missing_alt": missing_alt,
            "decorative": decorative
        }


# Convenience functions
def generate_aria_label(component_type: str, content: str, context: Optional[str] = None) -> str:
    """Generate ARIA label (convenience function)."""
    generator = ARIAGenerator()
    return generator.generate_label(component_type, content, context)


def generate_skip_link(target_id: str, text: str = "Skip to main content") -> str:
    """Generate skip-to-content link (convenience function)."""
    manager = FocusManager()
    return manager.generate_skip_link(target_id, text)
