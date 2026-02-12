#!/usr/bin/env python3
"""
validate_integration.py

Validates the FastAPI integration code structure without running it.
Checks imports, syntax, and API design.

Author: Ficio Prep Team
Date: February 2026
"""

import sys
import ast
import json
from pathlib import Path
from typing import List, Dict, Tuple

class Colors:
    """ANSI color codes"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    """Print formatted header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.RESET}\n")

def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓{Colors.RESET} {text}")

def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}✗{Colors.RESET} {text}")

def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠{Colors.RESET} {text}")

def check_file_exists(filepath: str) -> bool:
    """Check if file exists"""
    path = Path(filepath)
    if path.exists():
        print_success(f"File exists: {filepath}")
        return True
    else:
        print_error(f"File missing: {filepath}")
        return False

def check_python_syntax(filepath: str) -> Tuple[bool, str]:
    """Check Python file syntax"""
    try:
        with open(filepath, 'r') as f:
            code = f.read()
        ast.parse(code)
        return True, "Syntax valid"
    except SyntaxError as e:
        return False, f"Syntax error at line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)

def extract_endpoints(filepath: str) -> List[Dict[str, str]]:
    """Extract API endpoints from FastAPI main.py"""
    try:
        with open(filepath, 'r') as f:
            code = f.read()
        
        tree = ast.parse(code)
        endpoints = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Look for FastAPI decorators
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call):
                        if hasattr(decorator.func, 'attr'):
                            method = decorator.func.attr
                            if method in ['get', 'post', 'delete', 'put', 'patch', 'websocket']:
                                if decorator.args:
                                    path = decorator.args[0]
                                    if isinstance(path, ast.Constant):
                                        endpoints.append({
                                            'method': method.upper(),
                                            'path': path.value,
                                            'function': node.name
                                        })
        
        return endpoints
    except Exception as e:
        print_error(f"Failed to extract endpoints: {e}")
        return []

def check_config_json(filepath: str) -> Tuple[bool, List[str]]:
    """Validate config.json structure"""
    issues = []
    
    try:
        with open(filepath, 'r') as f:
            config = json.load(f)
        
        # Check required sections
        if 'system_settings' not in config:
            issues.append("Missing 'system_settings' section")
        else:
            settings = config['system_settings']
            required_settings = ['num_bays', 'cv_grading_mode', 'camera_index']
            for setting in required_settings:
                if setting not in settings:
                    issues.append(f"Missing system setting: {setting}")
        
        if 'vegetables' not in config:
            issues.append("Missing 'vegetables' section")
        elif not isinstance(config['vegetables'], list):
            issues.append("'vegetables' must be a list")
        else:
            for veg in config['vegetables']:
                if 'id' not in veg:
                    issues.append(f"Vegetable missing 'id': {veg.get('name', 'unknown')}")
                if 'supported_cuts' not in veg:
                    issues.append(f"Vegetable missing 'supported_cuts': {veg.get('id', 'unknown')}")
        
        if 'cut_types' not in config:
            issues.append("Missing 'cut_types' section")
        
        return len(issues) == 0, issues
        
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON: {e}"]
    except Exception as e:
        return False, [str(e)]

def main():
    """Run validation checks"""
    print_header("FASTAPI INTEGRATION VALIDATION")
    
    all_passed = True
    
    # ========================================================================
    # FILE STRUCTURE CHECK
    # ========================================================================
    print_header("1. File Structure")
    
    required_files = {
        'Backend API': [
            'backend/api/main.py',
            'backend/api/models.py',
            'backend/api/task_manager.py',
        ],
        'Backend Core': [
            'backend/config/config_manager.py',
            'backend/cv/camera_manager.py',
            'backend/workflows/standard_workflow.py',
        ],
        'Configuration': [
            'config.json',
        ],
        'Documentation': [
            'README.md',
            'requirements.txt',
        ],
        'Testing': [
            'test_api_integration.py',
        ]
    }
    
    for category, files in required_files.items():
        print(f"\n{Colors.BOLD}{category}:{Colors.RESET}")
        for filepath in files:
            if not check_file_exists(filepath):
                all_passed = False
    
    # ========================================================================
    # SYNTAX CHECK
    # ========================================================================
    print_header("2. Python Syntax Validation")
    
    python_files = [
        'backend/api/main.py',
        'backend/api/models.py',
        'backend/api/task_manager.py',
        'backend/config/config_manager.py',
        'backend/cv/camera_manager.py',
        'backend/workflows/standard_workflow.py',
        'test_api_integration.py',
    ]
    
    for filepath in python_files:
        if Path(filepath).exists():
            valid, message = check_python_syntax(filepath)
            if valid:
                print_success(f"{filepath}: {message}")
            else:
                print_error(f"{filepath}: {message}")
                all_passed = False
    
    # ========================================================================
    # CONFIGURATION CHECK
    # ========================================================================
    print_header("3. Configuration Validation")
    
    if Path('config.json').exists():
        valid, issues = check_config_json('config.json')
        if valid:
            print_success("config.json: Valid structure")
        else:
            print_error("config.json: Issues found:")
            for issue in issues:
                print(f"  - {issue}")
            all_passed = False
    
    # ========================================================================
    # API ENDPOINTS CHECK
    # ========================================================================
    print_header("4. API Endpoints")
    
    if Path('backend/api/main.py').exists():
        endpoints = extract_endpoints('backend/api/main.py')
        
        if endpoints:
            print(f"Found {len(endpoints)} endpoints:\n")
            
            # Group by category
            categories = {
                'Configuration': [],
                'Tasks': [],
                'System': [],
                'Camera': [],
                'WebSocket': [],
                'Other': []
            }
            
            for ep in endpoints:
                path = ep['path']
                if '/vegetables' in path or '/cut-types' in path:
                    categories['Configuration'].append(ep)
                elif '/tasks' in path:
                    categories['Tasks'].append(ep)
                elif '/status' in path or '/emergency' in path or '/health' in path:
                    categories['System'].append(ep)
                elif '/camera' in path:
                    categories['Camera'].append(ep)
                elif path.startswith('/ws'):
                    categories['WebSocket'].append(ep)
                else:
                    categories['Other'].append(ep)
            
            for category, eps in categories.items():
                if eps:
                    print(f"{Colors.BOLD}{category}:{Colors.RESET}")
                    for ep in eps:
                        method_color = Colors.GREEN if ep['method'] == 'GET' else Colors.YELLOW
                        print(f"  {method_color}{ep['method']:<6}{Colors.RESET} {ep['path']}")
            
            print_success(f"\nTotal endpoints: {len(endpoints)}")
        else:
            print_warning("No endpoints found (may need full AST parsing)")
    
    # ========================================================================
    # INTEGRATION CHECKLIST
    # ========================================================================
    print_header("5. Integration Checklist")
    
    checklist = [
        ("FastAPI application created", Path('backend/api/main.py').exists()),
        ("Pydantic models defined", Path('backend/api/models.py').exists()),
        ("Task manager implemented", Path('backend/api/task_manager.py').exists()),
        ("Configuration system ready", Path('backend/config/config_manager.py').exists()),
        ("Camera interface ready", Path('backend/cv/camera_manager.py').exists()),
        ("Workflow system ready", Path('backend/workflows/standard_workflow.py').exists()),
        ("Test suite created", Path('test_api_integration.py').exists()),
        ("Documentation complete", Path('README.md').exists()),
        ("Requirements specified", Path('requirements.txt').exists()),
        ("Config file present", Path('config.json').exists()),
    ]
    
    passed = 0
    for item, status in checklist:
        if status:
            print_success(item)
            passed += 1
        else:
            print_error(item)
    
    print(f"\n{Colors.BOLD}Checklist: {passed}/{len(checklist)} items complete{Colors.RESET}")
    
    # ========================================================================
    # SUMMARY
    # ========================================================================
    print_header("VALIDATION SUMMARY")
    
    if all_passed and passed == len(checklist):
        print(f"{Colors.GREEN}{Colors.BOLD}✓ ALL CHECKS PASSED{Colors.RESET}")
        print("\nThe FastAPI integration is ready!")
        print("\nNext steps:")
        print("  1. Install dependencies: pip install -r requirements.txt")
        print("  2. Start server: ./start_api.sh")
        print("  3. Access docs: http://localhost:8000/docs")
        print("  4. Run tests: pytest test_api_integration.py -v")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}✗ VALIDATION FAILED{Colors.RESET}")
        print("\nPlease fix the issues above before proceeding.")
        return 1

if __name__ == "__main__":
    sys.exit(main())