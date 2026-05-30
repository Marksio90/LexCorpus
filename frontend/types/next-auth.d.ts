import "next-auth";

declare module "next-auth" {
  interface Session {
    user: {
      id:                    string;
      name?:                 string | null;
      email?:                string | null;
      image?:                string | null;
      tier:                  string;
      admin:                 boolean;
      onboardingCompletedAt: Date | null;
    };
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    onboardingCompletedAt?: Date | null;
  }
}
