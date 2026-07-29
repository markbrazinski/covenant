type RevealClaim = {
  ownerId: string;
  completed: boolean;
};

export class FirstRevealRegistry {
  private readonly claims = new Map<string, RevealClaim>();

  claim(key: string, ownerId: string): boolean {
    const existing = this.claims.get(key);
    if (!existing) {
      this.claims.set(key, { ownerId, completed: false });
      return true;
    }
    return existing.ownerId === ownerId && !existing.completed;
  }

  complete(key: string, ownerId: string): void {
    const existing = this.claims.get(key);
    if (existing?.ownerId === ownerId) {
      existing.completed = true;
    }
  }
}

// Module lifetime equals the current page lifetime: navigation and lifecycle
// rerenders share the registry, while a full reload gets one fresh reveal.
export const pageFirstRevealRegistry = new FirstRevealRegistry();
