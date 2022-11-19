#!/usr/bin/python3.9
from charm.toolbox.ecgroup import ECGroup, G, ZR
from charm.toolbox.eccurve import prime192v2


class SecretShare:
    def __init__(self, element):
        self.elem = element

    def genShares(self, secret, k = 0, n = 0):
        q = [self.elem.random(ZR) for i in range(0, k)]
        q[0] = secret
        shares = {}
        for i in range(0, n+1):
            shares[i] = 0
            for j in range(0, k):
                shares[i] += q[j] * (i**j)
        return shares

    def recover(self, shares):
        indexes = shares.keys()
        output = 0
        for i in indexes:
            coeff = 1
            for j in indexes:
                if i!=j:
                    coeff *= -j * (self.elem.init(ZR, (i-j))**(-1))
            output += coeff*shares[i]
        return output

    def recoverInExp(self, shares):
        indexes = shares.keys()
        output = self.elem.random(G)**0
        for i in indexes:
            coeff = 1
            for j in indexes:
                if i!=j:
                    coeff *= -j * (self.elem.init(ZR, (i-j))**(-1))
            output *= shares[i]**coeff
        return output

