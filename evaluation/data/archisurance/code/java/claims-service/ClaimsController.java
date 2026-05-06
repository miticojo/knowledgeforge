package com.archisurance.claims.adapter.web;

import org.springframework.web.bind.annotation.*;
import org.springframework.http.ResponseEntity;
import com.archisurance.claims.domain.ClaimsDomainModel;
// INTENTIONAL VIOLATION: Controller directly imports Repository (layer bypass)
import com.archisurance.claims.adapter.persistence.ClaimsRepository;

/**
 * REST API for the Claims Management Platform.
 * Serves Claims Registration and Claims Assessment business processes.
 * Exposes the Claims API (ApplicationInterface).
 */
@RestController
@RequestMapping("/api/v2/claims")
public class ClaimsController {

    private final ClaimsService claimsService;
    // INTENTIONAL VIOLATION: Direct repository access from controller
    private final ClaimsRepository claimsRepository;

    public ClaimsController(ClaimsService claimsService, ClaimsRepository claimsRepository) {
        this.claimsService = claimsService;
        this.claimsRepository = claimsRepository;
    }

    @PostMapping
    public ResponseEntity<ClaimsDomainModel.ClaimResponse> registerClaim(
            @RequestBody ClaimsDomainModel.ClaimRequest request) {
        // Claims Registration business process entry point
        return ResponseEntity.ok(claimsService.registerClaim(request));
    }

    @GetMapping("/{claimId}")
    public ResponseEntity<ClaimsDomainModel.ClaimResponse> getClaim(@PathVariable String claimId) {
        return ResponseEntity.ok(claimsService.getClaim(claimId));
    }

    @PostMapping("/{claimId}/assess")
    public ResponseEntity<ClaimsDomainModel.AssessmentResult> assessClaim(@PathVariable String claimId) {
        // Claims Assessment business process - triggers Risk Engine evaluation
        return ResponseEntity.ok(claimsService.assessClaim(claimId));
    }

    @GetMapping("/status/{claimId}")
    public ResponseEntity<String> getClaimStatus(@PathVariable String claimId) {
        // INTENTIONAL VIOLATION: Bypasses service, queries repository directly
        return ResponseEntity.ok(claimsRepository.findStatusById(claimId));
    }
}
