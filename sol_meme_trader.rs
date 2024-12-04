use anchor_lang::prelude::*;
use anchor_spl::token::{self, Mint, Token, TokenAccount, Transfer};

declare_id!("MEMETRADINGPROG1111111111111111111111111111");

#[program]
pub mod meme_coin_trading {
    use super::*;

    /// Buy meme coins by paying in SOL
    pub fn buy_meme_coins(ctx: Context<BuyMemeCoins>, sol_amount: u64) -> Result<()> {
        let buyer = &ctx.accounts.buyer;
        let treasury = &ctx.accounts.treasury;

        // Transfer SOL from buyer to treasury
        **treasury.try_borrow_mut_lamports()? += sol_amount;
        **buyer.try_borrow_mut_lamports()? -= sol_amount;

        // Transfer meme coins to the buyer
        let seeds = &[treasury.key().as_ref()];
        let signer = &[&seeds[..]];
        let cpi_accounts = Transfer {
            from: ctx.accounts.treasury_token_account.to_account_info(),
            to: ctx.accounts.buyer_token_account.to_account_info(),
            authority: ctx.accounts.treasury.to_account_info(),
        };
        let cpi_program = ctx.accounts.token_program.to_account_info();
        token::transfer(CpiContext::new_with_signer(cpi_program, cpi_accounts, signer), sol_amount)?;

        Ok(())
    }

    /// Sell meme coins in exchange for SOL
    pub fn sell_meme_coins(ctx: Context<SellMemeCoins>, coin_amount: u64) -> Result<()> {
        let buyer = &ctx.accounts.buyer;
        let treasury = &ctx.accounts.treasury;

        // Transfer meme coins from the user to the treasury
        let cpi_accounts = Transfer {
            from: ctx.accounts.buyer_token_account.to_account_info(),
            to: ctx.accounts.treasury_token_account.to_account_info(),
            authority: ctx.accounts.buyer.to_account_info(),
        };
        let cpi_program = ctx.accounts.token_program.to_account_info();
        token::transfer(CpiContext::new(cpi_program, cpi_accounts), coin_amount)?;

        // Transfer SOL from treasury to the user
        let sol_to_return = coin_amount; // 1:1 exchange rate (for simplicity)
        **treasury.try_borrow_mut_lamports()? -= sol_to_return;
        **buyer.try_borrow_mut_lamports()? += sol_to_return;

        Ok(())
    }
}

#[derive(Accounts)]
pub struct BuyMemeCoins<'info> {
    #[account(mut)]
    pub buyer: Signer<'info>,
    /// CHECK: This is safe because we are only transferring SOL
    #[account(mut)]
    pub treasury: UncheckedAccount<'info>,
    #[account(mut)]
    pub treasury_token_account: Box<Account<'info, TokenAccount>>,
    #[account(mut)]
    pub buyer_token_account: Box<Account<'info, TokenAccount>>,
    pub token_program: Program<'info, Token>,
}

#[derive(Accounts)]
pub struct SellMemeCoins<'info> {
    #[account(mut)]
    pub buyer: Signer<'info>,
    /// CHECK: This is safe because we are only transferring SOL
    #[account(mut)]
    pub treasury: UncheckedAccount<'info>,
    #[account(mut)]
    pub treasury_token_account: Box<Account<'info, TokenAccount>>,
    #[account(mut)]
    pub buyer_token_account: Box<Account<'info, TokenAccount>>,
    pub token_program: Program<'info, Token>,
}
