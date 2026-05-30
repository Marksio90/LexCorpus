-- CreateTable
CREATE TABLE "Account" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "providerAccountId" TEXT NOT NULL,
    "refresh_token" TEXT,
    "access_token" TEXT,
    "expires_at" INTEGER,
    "token_type" TEXT,
    "scope" TEXT,
    "id_token" TEXT,
    "session_state" TEXT,

    CONSTRAINT "Account_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Session" (
    "id" TEXT NOT NULL,
    "sessionToken" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "expires" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Session_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "User" (
    "id" TEXT NOT NULL,
    "name" TEXT,
    "email" TEXT,
    "emailVerified" TIMESTAMP(3),
    "image" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "newsletterEnabled" BOOLEAN NOT NULL DEFAULT true,
    "newsletterLastSentAt" TIMESTAMP(3),
    "tier" TEXT NOT NULL DEFAULT 'free',
    "tierExpiresAt" TIMESTAMP(3),
    "stripeCustomerId" TEXT,
    "stripeSubscriptionId" TEXT,
    "stripePriceId" TEXT,

    CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "LegalChange" (
    "id" TEXT NOT NULL,
    "detectedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "actId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "sourceType" TEXT NOT NULL,
    "year" INTEGER,
    "summary" TEXT NOT NULL,
    "chunkText" TEXT NOT NULL,
    "url" TEXT,

    CONSTRAINT "LegalChange_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "LegalAlert" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "changeId" TEXT NOT NULL,
    "similarity" DOUBLE PRECISION NOT NULL,
    "question" TEXT NOT NULL,
    "readAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "LegalAlert_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "VerificationToken" (
    "identifier" TEXT NOT NULL,
    "token" TEXT NOT NULL,
    "expires" TIMESTAMP(3) NOT NULL
);

-- CreateTable
CREATE TABLE "QueryLog" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "question" TEXT NOT NULL,
    "answer" TEXT NOT NULL,
    "sources" TEXT NOT NULL,
    "modelUsed" TEXT NOT NULL,
    "retrievalUsed" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "QueryLog_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Feedback" (
    "id" TEXT NOT NULL,
    "queryLogId" TEXT NOT NULL,
    "userId" TEXT,
    "rating" INTEGER NOT NULL,
    "comment" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Feedback_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ApiToken" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "tokenHash" TEXT NOT NULL,
    "prefix" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "lastUsedAt" TIMESTAMP(3),
    "revokedAt" TIMESTAMP(3),
    "requestCount" INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT "ApiToken_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "PrivateDocument" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "filename" TEXT NOT NULL,
    "mimeType" TEXT NOT NULL,
    "sizeBytes" INTEGER NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'processing',
    "errorMsg" TEXT,
    "chunkCount" INTEGER NOT NULL DEFAULT 0,
    "uploadedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "processedAt" TIMESTAMP(3),

    CONSTRAINT "PrivateDocument_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SharedReport" (
    "id" TEXT NOT NULL,
    "token" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "question" TEXT NOT NULL,
    "answer" TEXT NOT NULL,
    "sources" TEXT NOT NULL,
    "modelUsed" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expiresAt" TIMESTAMP(3),

    CONSTRAINT "SharedReport_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "WidgetConfig" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "token" TEXT NOT NULL,
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "title" TEXT NOT NULL DEFAULT 'Asystent prawny',
    "welcomeMsg" TEXT NOT NULL DEFAULT 'Cześć! Jestem asystentem prawnym. W czym mogę pomóc?',
    "accentColor" TEXT NOT NULL DEFAULT '#2563eb',
    "logoUrl" TEXT,
    "allowedDomains" TEXT NOT NULL DEFAULT '*',
    "requestCount" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "WidgetConfig_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ExpertRequest" (
    "id" TEXT NOT NULL,
    "requesterId" TEXT NOT NULL,
    "question" TEXT NOT NULL,
    "context" TEXT,
    "status" TEXT NOT NULL DEFAULT 'open',
    "expertId" TEXT,
    "response" TEXT,
    "respondedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ExpertRequest_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "RegistrySubscription" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "actId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "url" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "RegistrySubscription_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "UsageLog" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "date" TEXT NOT NULL,
    "count" INTEGER NOT NULL DEFAULT 0,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "UsageLog_pkey" PRIMARY KEY ("id")
);

-- CreateUniqueIndex
CREATE UNIQUE INDEX "Account_provider_providerAccountId_key" ON "Account"("provider", "providerAccountId");

-- CreateUniqueIndex
CREATE UNIQUE INDEX "Session_sessionToken_key" ON "Session"("sessionToken");

-- CreateUniqueIndex
CREATE UNIQUE INDEX "User_email_key" ON "User"("email");

-- CreateUniqueIndex
CREATE UNIQUE INDEX "User_stripeCustomerId_key" ON "User"("stripeCustomerId");

-- CreateUniqueIndex
CREATE UNIQUE INDEX "User_stripeSubscriptionId_key" ON "User"("stripeSubscriptionId");

-- CreateIndex
CREATE INDEX "LegalChange_actId_idx" ON "LegalChange"("actId");

-- CreateIndex
CREATE INDEX "LegalChange_detectedAt_idx" ON "LegalChange"("detectedAt" DESC);

-- CreateIndex
CREATE INDEX "LegalChange_sourceType_idx" ON "LegalChange"("sourceType");

-- CreateUniqueIndex
CREATE UNIQUE INDEX "LegalAlert_userId_changeId_key" ON "LegalAlert"("userId", "changeId");

-- CreateIndex
CREATE INDEX "LegalAlert_userId_readAt_idx" ON "LegalAlert"("userId", "readAt");

-- CreateUniqueIndex
CREATE UNIQUE INDEX "VerificationToken_token_key" ON "VerificationToken"("token");

-- CreateUniqueIndex
CREATE UNIQUE INDEX "VerificationToken_identifier_token_key" ON "VerificationToken"("identifier", "token");

-- CreateIndex
CREATE INDEX "QueryLog_userId_createdAt_idx" ON "QueryLog"("userId", "createdAt" DESC);

-- CreateIndex
CREATE INDEX "QueryLog_createdAt_idx" ON "QueryLog"("createdAt" DESC);

-- CreateUniqueIndex
CREATE UNIQUE INDEX "Feedback_queryLogId_key" ON "Feedback"("queryLogId");

-- CreateIndex
CREATE INDEX "Feedback_rating_idx" ON "Feedback"("rating");

-- CreateIndex
CREATE INDEX "Feedback_createdAt_idx" ON "Feedback"("createdAt" DESC);

-- CreateIndex
CREATE INDEX "Feedback_userId_idx" ON "Feedback"("userId");

-- CreateIndex
CREATE INDEX "ApiToken_userId_idx" ON "ApiToken"("userId");

-- CreateUniqueIndex
CREATE UNIQUE INDEX "ApiToken_tokenHash_key" ON "ApiToken"("tokenHash");

-- CreateIndex
CREATE INDEX "PrivateDocument_userId_status_idx" ON "PrivateDocument"("userId", "status");

-- CreateIndex
CREATE INDEX "PrivateDocument_uploadedAt_idx" ON "PrivateDocument"("uploadedAt" DESC);

-- CreateUniqueIndex
CREATE UNIQUE INDEX "SharedReport_token_key" ON "SharedReport"("token");

-- CreateIndex
CREATE INDEX "SharedReport_token_idx" ON "SharedReport"("token");

-- CreateUniqueIndex
CREATE UNIQUE INDEX "WidgetConfig_userId_key" ON "WidgetConfig"("userId");

-- CreateUniqueIndex
CREATE UNIQUE INDEX "WidgetConfig_token_key" ON "WidgetConfig"("token");

-- CreateIndex
CREATE INDEX "ExpertRequest_status_createdAt_idx" ON "ExpertRequest"("status", "createdAt" DESC);

-- CreateIndex
CREATE INDEX "ExpertRequest_requesterId_idx" ON "ExpertRequest"("requesterId");

-- CreateUniqueIndex
CREATE UNIQUE INDEX "RegistrySubscription_userId_actId_key" ON "RegistrySubscription"("userId", "actId");

-- CreateIndex
CREATE INDEX "RegistrySubscription_actId_idx" ON "RegistrySubscription"("actId");

-- CreateIndex
CREATE INDEX "RegistrySubscription_userId_idx" ON "RegistrySubscription"("userId");

-- CreateUniqueIndex
CREATE UNIQUE INDEX "UsageLog_userId_date_key" ON "UsageLog"("userId", "date");

-- CreateIndex
CREATE INDEX "UsageLog_userId_idx" ON "UsageLog"("userId");

-- AddForeignKey
ALTER TABLE "Account" ADD CONSTRAINT "Account_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Session" ADD CONSTRAINT "Session_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "LegalAlert" ADD CONSTRAINT "LegalAlert_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "LegalAlert" ADD CONSTRAINT "LegalAlert_changeId_fkey" FOREIGN KEY ("changeId") REFERENCES "LegalChange"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "QueryLog" ADD CONSTRAINT "QueryLog_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Feedback" ADD CONSTRAINT "Feedback_queryLogId_fkey" FOREIGN KEY ("queryLogId") REFERENCES "QueryLog"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ApiToken" ADD CONSTRAINT "ApiToken_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PrivateDocument" ADD CONSTRAINT "PrivateDocument_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "WidgetConfig" ADD CONSTRAINT "WidgetConfig_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ExpertRequest" ADD CONSTRAINT "ExpertRequest_requesterId_fkey" FOREIGN KEY ("requesterId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ExpertRequest" ADD CONSTRAINT "ExpertRequest_expertId_fkey" FOREIGN KEY ("expertId") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "RegistrySubscription" ADD CONSTRAINT "RegistrySubscription_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "UsageLog" ADD CONSTRAINT "UsageLog_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
