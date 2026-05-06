/**
 * Customer Self-Service Portal -- ApplicationInterface: Mobile App Interface
 *
 * Serves: Customer Onboarding, Complaint Handling (BusinessProcess)
 * Used by: Customer (BusinessActor)
 */
import { Controller, Get, Post, Body, Param, UseGuards } from '@nestjs/common';
import { CustomerService } from './customer.service';
import { CreateCustomerDto, CustomerResponseDto } from './customer.entity';
import { AuthGuard } from '@nestjs/passport';

@Controller('api/v1/customers')
@UseGuards(AuthGuard('jwt'))
export class CustomerController {

  constructor(private readonly customerService: CustomerService) {}

  @Post()
  async createCustomer(@Body() dto: CreateCustomerDto): Promise<CustomerResponseDto> {
    // Customer Onboarding business process entry point
    // Triggers Customer Identity Verification via IAM
    return this.customerService.onboard(dto);
  }

  @Get(':customerId')
  async getCustomer(@Param('customerId') id: string): Promise<CustomerResponseDto> {
    return this.customerService.findById(id);
  }

  @Get(':customerId/claims')
  async getCustomerClaims(@Param('customerId') id: string) {
    // Cross-service call to Claims Management Platform
    return this.customerService.getClaimsForCustomer(id);
  }

  @Post(':customerId/complaints')
  async fileComplaint(@Param('customerId') id: string, @Body() complaint: any) {
    // Complaint Handling business process
    return this.customerService.fileComplaint(id, complaint);
  }
}
