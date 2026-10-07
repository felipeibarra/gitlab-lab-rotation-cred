"""Deterministic domain validation; prices are integer cents, never floats."""
from __future__ import annotations

def validate_catalog(data):
    if not isinstance(data, dict) or not isinstance(data.get('products'), list):
        raise ValueError('products debe ser una lista')
    if not 1 <= len(data['products']) <= 100:
        raise ValueError('cantidad de productos fuera de rango')
    seen = set()
    for product in data['products']:
        if not isinstance(product, dict):
            raise ValueError('cada producto debe ser un objeto')
        sku = product.get('sku')
        price = product.get('price_cents')
        if not isinstance(sku, str) or not sku or len(sku) > 50 or sku in seen:
            raise ValueError('SKU inválido o repetido')
        if type(price) is not int or not 1 <= price <= 100000000:
            raise ValueError('precio inválido')
        seen.add(sku)
    return data

def order_total(catalog, sku, quantity):
    if type(quantity) is not int or not 1 <= quantity <= 100:
        raise ValueError('quantity debe ser un entero entre 1 y 100')
    validate_catalog(catalog)
    product = next((p for p in catalog['products'] if p['sku'] == sku), None)
    if product is None:
        raise ValueError('SKU desconocido')
    return product['price_cents'] * quantity
