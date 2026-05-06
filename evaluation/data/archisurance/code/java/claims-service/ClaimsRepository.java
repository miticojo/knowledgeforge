package com.archisurance.claims.adapter.persistence;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

/**
 * Data access layer for Claims Management Platform.
 * Accesses: Claim Record (DataObject) stored in PostgreSQL 15 (SystemSoftware).
 * Also accesses Customer Profile for claim validation.
 */
@Repository
public interface ClaimsRepository extends JpaRepository<ClaimEntity, String> {

    @Query("SELECT c.status FROM ClaimEntity c WHERE c.claimId = :claimId")
    String findStatusById(String claimId);

    @Query("SELECT c FROM ClaimEntity c WHERE c.customerId = :customerId ORDER BY c.createdAt DESC")
    List<ClaimEntity> findByCustomerId(String customerId);

    @Query("SELECT c FROM ClaimEntity c WHERE c.status = 'PENDING_ASSESSMENT'")
    List<ClaimEntity> findPendingAssessments();
}
